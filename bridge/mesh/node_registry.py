"""
Node Registry: The directory of every breaker panel in the neighborhood.

ELI5: This is like the clipboard on the electrician's truck.
      It lists every house (node), what size service panel it has (GPU tier),
      whether the lights are on (status), and how to knock on the door (IP).
      When a new house gets built, we add it. When it burns down, we cross it out.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import struct
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from mesh_configurator import NodeSpec


# ═══════════════════════════════════════════════════════════════════════════════
# In-memory Registry
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class RegistryState:
    """
    ELI5: This is the filing cabinet inside the truck.
          Every drawer (slot) holds one house's paperwork.
    """
    nodes: Dict[str, NodeSpec] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


# Singleton truck-clipboard. In production you'd back this with Redis / etcd.
_registry = RegistryState()


# ═══════════════════════════════════════════════════════════════════════════════
# CRUD Operations
# ═══════════════════════════════════════════════════════════════════════════════

async def register_node(node: NodeSpec) -> None:
    """
    ELI5: A new house just got built on the block.
          We walk over, read the nameplate, and write it on our clipboard.
    """
    async with _registry.lock:
        node.last_seen = datetime.utcnow()
        _registry.nodes[node.id] = node


def register_node_sync(node: NodeSpec) -> None:
    """
    ELI5: Same as above, but the electrician is in a hurry and
          doesn't want to wait for the walkie-talkie (async event loop).
    """
    node.last_seen = datetime.utcnow()
    _registry.nodes[node.id] = node


async def deregister_node(node_id: str) -> bool:
    """
    ELI5: A house got demolished. We cross it off the clipboard
          so we don't waste time knocking on an empty lot.
    """
    async with _registry.lock:
        if node_id in _registry.nodes:
            del _registry.nodes[node_id]
            return True
        return False


def deregister_node_sync(node_id: str) -> bool:
    if node_id in _registry.nodes:
        del _registry.nodes[node_id]
        return True
    return False


async def get_node(node_id: str) -> Optional[NodeSpec]:
    """ELI5: "Hey, what's the address for the blue house on Maple?"""
    async with _registry.lock:
        return _registry.nodes.get(node_id)


def get_node_sync(node_id: str) -> Optional[NodeSpec]:
    return _registry.nodes.get(node_id)


async def list_nodes() -> List[NodeSpec]:
    """ELI5: Hand me the whole clipboard; I want to see every house on the route."""
    async with _registry.lock:
        return list(_registry.nodes.values())


def list_nodes_sync() -> List[NodeSpec]:
    return list(_registry.nodes.values())


# ═══════════════════════════════════════════════════════════════════════════════
# Discovery
# ═══════════════════════════════════════════════════════════════════════════════

_MULTICAST_GROUP = "239.255.42.99"
_DISCOVERY_PORT = 51999
_DISCOVERY_MAGIC = b"SIMPLEPOD_DISCOVER_v1"


async def discover_nodes(timeout: float = 5.0) -> List[NodeSpec]:
    """
    ELI5: The electrician stands on the sidewalk and yells
          "Any houses here?!" through a megaphone (multicast).
          Every house that shouts back gets added to the clipboard.

    Fallback: if nobody yells back, we check Tailscale's own directory
    (the phone book) to see who's currently online.
    """
    discovered: List[NodeSpec] = []

    # ── Attempt 1: UDP multicast shout ───────────────────────────────────────
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(timeout)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", _DISCOVERY_PORT))

        mreq = struct.pack("4sl", socket.inet_aton(_MULTICAST_GROUP), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        deadline = datetime.utcnow().timestamp() + timeout
        while datetime.utcnow().timestamp() < deadline:
            try:
                data, addr = sock.recvfrom(4096)
                if data.startswith(_DISCOVERY_MAGIC):
                    payload = json.loads(data[len(_DISCOVERY_MAGIC):].decode("utf-8"))
                    node = NodeSpec.model_validate(payload)
                    discovered.append(node)
                    async with _registry.lock:
                        _registry.nodes[node.id] = node
            except socket.timeout:
                break
            except Exception:
                continue
        sock.close()
    except Exception:
        pass  # Multicast is best-effort; fall through to Tailscale.

    # ── Attempt 2: Tailscale status JSON ─────────────────────────────────────
    try:
        import subprocess
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            ts_status = json.loads(result.stdout)
            for peer_id, peer_info in ts_status.get("Peer", {}).items():
                node_id = peer_info.get("HostName", peer_id)
                existing = await get_node(node_id)
                if existing is None:
                    node = NodeSpec(
                        id=node_id,
                        hostname=peer_info.get("HostName", node_id),
                        ip=peer_info.get("TailscaleIPs", ["unknown"])[0],
                        role="shadow_pc",  # Default; refined by user later
                        gpu_type="unknown",
                        status="online" if peer_info.get("Online") else "offline",
                        tailscale_ip=peer_info.get("TailscaleIPs", [None])[0],
                        last_seen=datetime.utcnow(),
                    )
                    discovered.append(node)
                    async with _registry.lock:
                        _registry.nodes[node.id] = node
    except Exception:
        pass

    return discovered


async def announce_presence(node: NodeSpec) -> None:
    """
    ELI5: Your house hears the electrician's megaphone and yells back
          "I'm here! I have a 200-amp panel and a Tesla charger!"
    """
    payload = json.dumps(node.model_dump(mode="json"), default=str).encode("utf-8")
    packet = _DISCOVERY_MAGIC + payload

    def _send() -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.sendto(packet, (_MULTICAST_GROUP, _DISCOVERY_PORT))
        sock.close()

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _send)


# ═══════════════════════════════════════════════════════════════════════════════
# GPU-Tier Lookup
# ═══════════════════════════════════════════════════════════════════════════════

async def get_node_by_gpu_tier(tier: str) -> Optional[NodeSpec]:
    """
    ELI5: The boss says "I need a house with at least a 400-amp panel
          to run the new kiln." We flip through the clipboard and
          return the first match, or shrug if nobody qualifies.
    """
    tier_lower = tier.lower()
    async with _registry.lock:
        for node in _registry.nodes.values():
            if node.gpu_type.lower() == tier_lower:
                return node
        return None


def get_node_by_gpu_tier_sync(tier: str) -> Optional[NodeSpec]:
    tier_lower = tier.lower()
    for node in _registry.nodes.values():
        if node.gpu_type.lower() == tier_lower:
            return node
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Persistence (simple JSON snapshot)
# ═══════════════════════════════════════════════════════════════════════════════

async def save_registry(path: str) -> None:
    """
    ELI5: At the end of the day, the electrician photocopies the clipboard
          and leaves it in the office filing cabinet so the night crew
          knows which houses still need work tomorrow.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    async with _registry.lock:
        snapshot = {nid: node.model_dump(mode="json") for nid, node in _registry.nodes.items()}
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _write_json, path, snapshot)


def _write_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)


async def load_registry(path: str) -> None:
    """
    ELI5: The morning shift grabs last night's photocopy from the filing cabinet
          and copies every entry back onto their fresh clipboard.
    """
    if not os.path.exists(path):
        return
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, _read_json, path)
    async with _registry.lock:
        for nid, payload in data.items():
            _registry.nodes[nid] = NodeSpec.model_validate(payload)


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
