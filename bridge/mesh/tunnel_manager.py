"""
Tunnel Manager: The switchboard operator for encrypted conduits.

ELI5: This is like the smart transfer switch between your main house
      (Shadow PC) and the workshop (Local MSI). When you flip the switch,
      power flows through an underground conduit (encrypted tunnel).
      The manager checks the wire gauge (bandwidth), listens for humming
      (latency), and shuts off the breaker if the wire gets too hot.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import math
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator, Dict, Optional

from mesh_configurator import NodeSpec, WireguardConfig, PeerConfig


# ═══════════════════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TunnelMetrics:
    """
    ELI5: The multimeter readings at both ends of the conduit:
          volts (throughput), amps (packet rate), and how long
          the signal takes to travel (latency).
    """
    tunnel_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    bytes_sent: int = 0
    bytes_received: int = 0
    packets_sent: int = 0
    packets_received: int = 0
    latency_ms: float = 0.0
    jitter_ms: float = 0.0
    packet_loss_pct: float = 0.0
    throughput_bps: float = 0.0
    is_relayed: bool = False
    nat_hole_punched: bool = False


@dataclass
class TunnelHandle:
    """
    ELI5: The breaker-switch label. It tells you which two rooms are connected,
          whether the switch is ON, and when it was last flipped.
    """
    tunnel_id: str
    source: NodeSpec
    target: NodeSpec
    wireguard_config: WireguardConfig
    established_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    is_open: bool = True
    _task: Optional[asyncio.Task] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Global State
# ═══════════════════════════════════════════════════════════════════════════════

_active_tunnels: Dict[str, TunnelHandle] = {}
_tunnel_lock = asyncio.Lock()


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _derive_tunnel_id(source_id: str, target_id: str) -> str:
    """
    ELI5: We need a serial number for every switch. We mash the two room names
          together in a blender (hash) so we always get the same label
          no matter which room you mention first.
    """
    combo = "::".join(sorted([source_id, target_id])).encode("utf-8")
    return base64.urlsafe_b64encode(
        hashlib.sha256(combo).digest()
    ).decode("ascii")[:16]


def _generate_psk() -> str:
    """
    ELI5: An extra padlock for the conduit. Both ends need the same key,
          but nobody else in the neighborhood can copy it.
    """
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


# ═══════════════════════════════════════════════════════════════════════════════
# Core Tunnel Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

async def establish_tunnel(source: NodeSpec, target: NodeSpec) -> TunnelHandle:
    """
    ELI5: The electrician digs a trench between two houses, lays armored cable,
          installs matching padlocks on both ends, and flips the breaker ON.
    """
    tunnel_id = _derive_tunnel_id(source.id, target.id)

    async with _tunnel_lock:
        if tunnel_id in _active_tunnels:
            existing = _active_tunnels[tunnel_id]
            if existing.is_open:
                return existing
            # Stale entry; remove it and rebuild.
            del _active_tunnels[tunnel_id]

    # Build WireGuard peer config for the target side.
    peer = PeerConfig(
        node_id=target.id,
        public_key=target.wireguard_pubkey or "PLACEHOLDER_PUBKEY",
        allowed_ips=[target.ip + "/32"],
        endpoint=f"{target.ip}:51820",
        persistent_keepalive=25,
        preshared_key=_generate_psk(),
    )

    # In a real deployment you'd pull the private key from a secrets manager.
    wg_config = WireguardConfig(
        node_id=source.id,
        private_key=base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
        listen_port=51820,
        address=f"10.200.0.{hash(source.id) % 254 + 1}/32",
        peers=[peer],
        nat_traversal=True,
        relay_fallback=True,
        keepalive_interval=25,
    )

    handle = TunnelHandle(
        tunnel_id=tunnel_id,
        source=source,
        target=target,
        wireguard_config=wg_config,
    )

    async with _tunnel_lock:
        _active_tunnels[tunnel_id] = handle

    # Start background health monitor.
    handle._task = asyncio.create_task(
        _background_monitor(handle),
        name=f"monitor-{tunnel_id}",
    )

    return handle


async def close_tunnel(tunnel: TunnelHandle) -> None:
    """
    ELI5: The homeowner decides they don't need the workshop powered anymore.
          The electrician flips the breaker OFF, removes the padlocks,
          and fills in the trench.
    """
    tunnel.is_open = False
    if tunnel._task and not tunnel._task.done():
        tunnel._task.cancel()
        try:
            await tunnel._task
        except asyncio.CancelledError:
            pass

    async with _tunnel_lock:
        if tunnel.tunnel_id in _active_tunnels:
            del _active_tunnels[tunnel.tunnel_id]


# ═══════════════════════════════════════════════════════════════════════════════
# Traffic Routing
# ═══════════════════════════════════════════════════════════════════════════════

async def route_traffic(tunnel: TunnelHandle, data: bytes) -> bytes:
    """
    ELI5: You flick the light switch in the main house; electrons race
          through the conduit, hit the workshop, and the light bulb
          flickers back a confirmation (response bytes).

    This is a logical shim. In production it would interface with
    the WireGuard TUN device or a userspace TCP/UDP proxy.
    """
    if not tunnel.is_open:
        raise RuntimeError(f"Tunnel {tunnel.tunnel_id} is closed — breaker is OFF.")

    tunnel.last_activity = datetime.utcnow()

    # Simulate wire traversal latency.
    await asyncio.sleep(0.005)

    # Simple echo with a transformation to prove end-to-end delivery.
    # Real code would write `data` into the WireGuard socket and await a response.
    response = b"ACK::" + base64.b64encode(hashlib.sha256(data).digest())
    return response


# ═══════════════════════════════════════════════════════════════════════════════
# Health Monitoring
# ═══════════════════════════════════════════════════════════════════════════════

async def monitor_tunnel_health(tunnel: TunnelHandle) -> AsyncIterator[TunnelMetrics]:
    """
    ELI5: The electrician clips a smart multimeter onto the conduit
          and it beeps out a new reading every few seconds:
          voltage drop, wire temperature, and whether the signal
          is going direct or bouncing through a neighborhood relay.
    """
    sent_history: list[tuple[float, int]] = []
    recv_history: list[tuple[float, int]] = []
    latencies: list[float] = []

    while tunnel.is_open:
        now = time.monotonic()

        # --- Ping probe -------------------------------------------------------
        probe_payload = secrets.token_bytes(64)
        t0 = time.monotonic()
        try:
            response = await route_traffic(tunnel, probe_payload)
            t1 = time.monotonic()
            rtt = (t1 - t0) * 1000.0
            latencies.append(rtt)
            if len(latencies) > 20:
                latencies.pop(0)
        except Exception:
            rtt = float("inf")
            latencies.append(rtt)

        # --- Derive jitter ----------------------------------------------------
        jitter = 0.0
        if len(latencies) >= 2:
            jitter = sum(
                abs(latencies[i] - latencies[i - 1])
                for i in range(1, len(latencies))
            ) / (len(latencies) - 1)

        # --- Simulate counters ------------------------------------------------
        # In production these would come from the WireGuard interface stats.
        sent_bytes = int(1024 * (1 + secrets.randbelow(10)))
        recv_bytes = int(1024 * (1 + secrets.randbelow(10)))
        sent_history.append((now, sent_bytes))
        recv_history.append((now, recv_bytes))
        # Trim history to last 5 s.
        cutoff = now - 5.0
        sent_history = [(t, b) for t, b in sent_history if t >= cutoff]
        recv_history = [(t, b) for t, b in recv_history if t >= cutoff]

        window = max(now - sent_history[0][0], 0.001) if sent_history else 1.0
        total_sent = sum(b for _, b in sent_history)
        total_recv = sum(b for _, b in recv_history)
        throughput = (total_sent + total_recv) * 8 / window

        packet_loss = 0.0
        if any(math.isinf(l) for l in latencies[-5:]):
            packet_loss = (sum(1 for l in latencies[-5:] if math.isinf(l)) / 5) * 100.0

        metrics = TunnelMetrics(
            tunnel_id=tunnel.tunnel_id,
            timestamp=datetime.utcnow(),
            bytes_sent=total_sent,
            bytes_received=total_recv,
            packets_sent=len(sent_history),
            packets_received=len(recv_history),
            latency_ms=latencies[-1] if latencies else 0.0,
            jitter_ms=jitter,
            packet_loss_pct=packet_loss,
            throughput_bps=throughput,
            is_relayed=rtt > 80.0,  # Heuristic: high RTT implies relay.
            nat_hole_punched=rtt < 80.0 and packet_loss == 0.0,
        )

        yield metrics
        await asyncio.sleep(2.0)


async def _background_monitor(tunnel: TunnelHandle) -> None:
    """
    ELI5: The quiet intern who sits in the utility room and stares at
          the smart-panel screen 24/7. If the wire hums funny for too long,
          they text the boss (log a warning) but keep the breaker on
          unless it actually catches fire.
    """
    try:
        async for metrics in monitor_tunnel_health(tunnel):
            if metrics.packet_loss_pct >= 100.0:
                # Dead wire — mark it but let the caller decide to close.
                tunnel.is_open = False
                break
    except asyncio.CancelledError:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# Utility
# ═══════════════════════════════════════════════════════════════════════════════

async def list_active_tunnels() -> list[TunnelHandle]:
    """ELI5: "Show me every conduit that's currently carrying power."""
    async with _tunnel_lock:
        return [t for t in _active_tunnels.values() if t.is_open]


async def get_tunnel(tunnel_id: str) -> Optional[TunnelHandle]:
    """ELI5: "What's the status of the conduit labeled #7?"""
    async with _tunnel_lock:
        return _active_tunnels.get(tunnel_id)
