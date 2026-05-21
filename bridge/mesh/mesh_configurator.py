"""
Mesh Configurator: The electrical blueprint drawer for your encrypted home network.

ELI5: This is like the drafting table where we draw the wiring diagrams
      for your smart home. Every outlet (node) gets a circuit number,
      every wire gets a gauge rating, and the inspector (validator)
      makes sure you won't trip the breaker before you flip the switch.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import os
import secrets
import subprocess
from datetime import datetime, timedelta
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic Config Models
# ═══════════════════════════════════════════════════════════════════════════════

class PeerConfig(BaseModel):
    """
    ELI5: This is like the label on the breaker panel telling you
          which room each breaker controls and what key opens it.
    """
    node_id: str = Field(..., description="Human-readable node identifier")
    public_key: str = Field(..., description="WireGuard public key (the lock face)")
    allowed_ips: List[str] = Field(default_factory=list, description="IP ranges this peer can reach")
    endpoint: Optional[str] = Field(None, description="Public IP:port where this peer listens")
    persistent_keepalive: int = Field(25, ge=0, le=65535, description="Seconds between keepalive pings")
    preshared_key: Optional[str] = Field(None, description="Optional extra padlock (PSK)")

    @field_validator("allowed_ips")
    @classmethod
    def _validate_cidrs(cls, v: List[str]) -> List[str]:
        """Make sure every 'wire' in the plan has a valid gauge rating."""
        for cidr in v:
            ipaddress.ip_network(cidr, strict=False)
        return v


class TailscaleConfig(BaseModel):
    """
    ELI5: This is like your subscription to the smart-home cloud service.
          It holds your account key, your house address, and the list of
          gadgets allowed on the network.
    """
    node_id: str
    auth_key: str = Field(..., repr=False)
    tailnet: str = Field("simplepod.ts.net", description="Your Tailscale network domain")
    advertise_routes: List[str] = Field(default_factory=list)
    accept_routes: bool = True
    shields_up: bool = False
    exit_node: bool = False
    ssh_enabled: bool = True
    tags: List[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("advertise_routes")
    @classmethod
    def _validate_routes(cls, v: List[str]) -> List[str]:
        for route in v:
            ipaddress.ip_network(route, strict=False)
        return v


class WireguardConfig(BaseModel):
    """
    ELI5: This is the physical lock-and-key set for one underground conduit.
          It knows the secret key for *this* end, and the public keys
          for every other end it needs to shake hands with.
    """
    node_id: str
    private_key: str = Field(..., repr=False)
    listen_port: int = Field(51820, ge=1, le=65535)
    address: str = Field("10.200.0.0/24", description="Internal mesh subnet for this node")
    dns: List[str] = Field(default_factory=lambda: ["1.1.1.1", "8.8.8.8"])
    mtu: int = Field(1280, ge=576, le=9000, description="Wire gauge: how fat the pipe is")
    peers: List[PeerConfig] = Field(default_factory=list)
    nat_traversal: bool = True
    relay_fallback: bool = True
    keepalive_interval: int = Field(25, ge=0, le=3600, description="Seconds between voltage-ping checks")
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("address")
    @classmethod
    def _validate_address(cls, v: str) -> str:
        ipaddress.ip_network(v, strict=False)
        return v


class NodeSpec(BaseModel):
    """
    ELI5: This is the nameplate on the electrical panel:
          which room it is, what size breaker it needs,
          and whether the lights are on right now.
    """
    id: str
    hostname: str
    ip: str
    role: str = Field(..., pattern="^(shadow_pc|local_msi|simplepod_rtx5090)$")
    gpu_type: str
    status: str = Field("offline", pattern="^(online|offline|busy|maintenance)$")
    tailscale_ip: Optional[str] = None
    wireguard_pubkey: Optional[str] = None
    last_seen: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MeshHealthReport(BaseModel):
    """
    ELI5: This is the electrician's clipboard after inspecting every outlet,
          breaker, and wire run. Green sticker = good, red sticker = call the boss.
    """
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_nodes: int = 0
    online_nodes: int = 0
    offline_nodes: int = 0
    latency_map: dict[str, float] = Field(default_factory=dict, description="node_id -> ms")
    packet_loss_map: dict[str, float] = Field(default_factory=dict, description="node_id -> %")
    nat_traversal_ok: bool = True
    relay_in_use: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        """True when every circuit is closed and no breakers are warm."""
        return self.offline_nodes == 0 and len(self.errors) == 0 and self.nat_traversal_ok


# ═══════════════════════════════════════════════════════════════════════════════
# Key Generation Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _generate_wireguard_keypair() -> tuple[str, str]:
    """
    ELI5: This is like cutting a new lock-and-key set at the hardware store.
          You get one secret key (hide it) and one public key (share it).
    """
    priv: bytes = secrets.token_bytes(32)
    pub: bytes = priv  # Simplified; real WireGuard does Curve25519 clamping
    # In production, call `wg genkey | wg pubkey` or use python-cryptography.
    private_b64: str = base64.b64encode(priv).decode("ascii")
    public_b64: str = base64.b64encode(pub).decode("ascii")
    return private_b64, public_b64


# ═══════════════════════════════════════════════════════════════════════════════
# Config Generators
# ═══════════════════════════════════════════════════════════════════════════════

def generate_tailscale_config(node_id: str, auth_key: str, **overrides: Any) -> TailscaleConfig:
    """
    ELI5: Hand the smart-home installer your account card (auth_key) and
          tell them which room (node_id) they're wiring up today.
          They'll stamp a blueprint you can hand to every device.
    """
    defaults = {
        "node_id": node_id,
        "auth_key": auth_key,
        "tailnet": "simplepod.ts.net",
        "advertise_routes": [],
        "accept_routes": True,
        "shields_up": False,
        "exit_node": False,
        "ssh_enabled": True,
        "tags": [f"tag:{node_id}"],
    }
    defaults.update(overrides)
    return TailscaleConfig.model_validate(defaults)


def generate_wireguard_config(
    node_id: str,
    private_key: str,
    peers: List[PeerConfig],
    **overrides: Any,
) -> WireguardConfig:
    """
    ELI5: You bring the secret key for your workshop's deadbolt,
          and a list of every neighbor's public lock face.
          We draw the conduit map, set the wire gauge (MTU),
          and decide how often to ping the voltage meter.
    """
    defaults = {
        "node_id": node_id,
        "private_key": private_key,
        "listen_port": 51820,
        "address": f"10.200.0.{hash(node_id) % 254 + 1}/32",
        "dns": ["1.1.1.1", "8.8.8.8"],
        "mtu": 1280,
        "peers": peers,
        "nat_traversal": True,
        "relay_fallback": True,
        "keepalive_interval": 25,
    }
    defaults.update(overrides)
    return WireguardConfig.model_validate(defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# Mesh Health Validation
# ═══════════════════════════════════════════════════════════════════════════════

async def validate_mesh_connectivity(nodes: List[NodeSpec]) -> MeshHealthReport:
    """
    ELI5: The master electrician walks through every room with a multimeter:
          checks voltage (latency), looks for dropped packets (flickering bulbs),
          and makes sure NAT holes (hidden wall cavities) aren't blocking the wire.
    """
    report = MeshHealthReport(total_nodes=len(nodes))

    for node in nodes:
        if node.status == "online":
            report.online_nodes += 1
        else:
            report.offline_nodes += 1

        # Simulate / execute lightweight probes
        latency_ms: float = 0.0
        packet_loss_pct: float = 0.0

        if node.tailscale_ip:
            try:
                # In production this would be an actual ICMP or Tailscale ping.
                result = subprocess.run(
                    ["tailscale", "ping", "--c", "3", "--timeout", "3s", node.tailscale_ip],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode != 0:
                    report.warnings.append(f"Tailscale ping failed for {node.id}")
                    packet_loss_pct = 100.0
                else:
                    # Naïve parser: real code would regex out the latency.
                    latency_ms = 12.0
                    packet_loss_pct = 0.0
            except Exception as exc:
                report.errors.append(f"Probe exception for {node.id}: {exc}")
                packet_loss_pct = 100.0
        else:
            report.warnings.append(f"No tailscale_ip for {node.id}; skipping direct probe")
            packet_loss_pct = 0.0  # Unknown, not necessarily dead

        report.latency_map[node.id] = latency_ms
        report.packet_loss_map[node.id] = packet_loss_pct

        # NAT & relay diagnostics
        if node.status == "online" and packet_loss_pct >= 100.0:
            report.nat_traversal_ok = False
            report.relay_in_use.append(node.id)

    return report


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience: dump / load
# ═══════════════════════════════════════════════════════════════════════════════

def dump_config_to_json(config: BaseModel, path: str) -> None:
    """
    ELI5: Photocopy the blueprint and file it in the cabinet (disk)
          so the next electrician knows what you did.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(config.model_dump(mode="json"), fh, indent=2, default=str)


def load_tailscale_config(path: str) -> TailscaleConfig:
    with open(path, "r", encoding="utf-8") as fh:
        return TailscaleConfig.model_validate_json(fh.read())


def load_wireguard_config(path: str) -> WireguardConfig:
    with open(path, "r", encoding="utf-8") as fh:
        return WireguardConfig.model_validate_json(fh.read())
