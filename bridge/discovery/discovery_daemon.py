"""
discovery_daemon.py

ELI5: This is the night-shift survey crew boss. Every 30 seconds he sends
      his team out to knock on every drawing station door in the building
      (and even the annex down the hall — local network IPs). The team
      checks which templates are loaded, times a quick sketch, peeks at
      the plotter paper tray, then radios the results back to the boss.
      The boss updates the master floor-plan (catalog) and blasts updates
      over the PA system so every crew in the building knows which stations
      are green, yellow, or red.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import signal
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set

import httpx
from pydantic import BaseModel, Field

from endpoint_catalog import (
    EndpointCatalog,
    EndpointStatus,
    LLMEndpoint,
    ModelInfo,
    Provider,
    get_default_catalog,
)
from health_checker import HealthReport, HealthStatus, probe_endpoint


# ──────────────────────────────────────────────────────────────────────────────
# Logging Setup
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("discovery_daemon")


# ──────────────────────────────────────────────────────────────────────────────
# Configuration Models
# ──────────────────────────────────────────────────────────────────────────────

class DiscoveryConfig(BaseModel):
    """ELI5: The boss's clipboard — which hallways to patrol and how often."""
    scan_interval_seconds: float = Field(default=30.0, description="Seconds between survey rounds")
    probe_timeout_seconds: float = Field(default=10.0, description="HTTP probe timeout")
    ollama_ports: List[int] = Field(default=[11434], description="Ports to check for Ollama")
    lmstudio_ports: List[int] = Field(default=[1234], description="Ports to check for LM Studio")
    local_networks: List[str] = Field(
        default=["127.0.0.1/32"],
        description="IP ranges to scan (CIDR notation). Use /24 for local LAN discovery.",
    )
    extra_hosts: List[str] = Field(
        default_factory=list,
        description="Additional specific host IPs or hostnames to probe every round",
    )


class HealthEvent(BaseModel):
    """ELI5: A single radio transmission from the survey team to the boss."""
    event_type: str = Field(..., description="upsert | remove | health_changed")
    endpoint: LLMEndpoint = Field(..., description="The endpoint that changed")
    previous_status: Optional[str] = Field(None, description="Previous status if changed")


# ──────────────────────────────────────────────────────────────────────────────
# Event Bus
# ──────────────────────────────────────────────────────────────────────────────

class EventBus:
    """ELI5: The office PA system. Anyone can plug in a speaker (subscriber)
    and hear announcements broadcast from the survey crew boss.
    """

    def __init__(self) -> None:
        self._subs: List[Callable[[HealthEvent], asyncio.Future[None] | None]] = []

    def subscribe(self, callback: Callable[[HealthEvent], asyncio.Future[None] | None]) -> None:
        """ELI5: Plug a new speaker into the PA jack."""
        self._subs.append(callback)

    def unsubscribe(self, callback: Callable[[HealthEvent], asyncio.Future[None] | None]) -> None:
        """ELI5: Unplug a speaker from the PA jack."""
        if callback in self._subs:
            self._subs.remove(callback)

    async def publish(self, event: HealthEvent) -> None:
        """ELI5: Hit the mic and speak to every plugged-in speaker."""
        for cb in list(self._subs):
            try:
                result = cb(event)
                if asyncio.isfuture(result) or asyncio.iscoroutine(result):
                    await result  # type: ignore[misc]
            except Exception as exc:
                logger.warning("PA speaker buzzed out: %s", exc)


# ──────────────────────────────────────────────────────────────────────────────
# Model Parsing Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _parse_ollama_models(data: Dict[str, Any]) -> List[ModelInfo]:
    """ELI5: Ollama hands us a stack of template cards in its own format;
    this helper flattens them into our standard recipe cards.
    """
    models: List[ModelInfo] = []
    raw_models = data.get("models", [])
    for raw in raw_models:
        if not isinstance(raw, dict):
            continue
        name = raw.get("name", "")
        # Ollama names often look like "llama3:8b-instruct-q4_K_M"
        parts = name.split(":")
        base_name = parts[0] if parts else name
        tag = parts[1] if len(parts) > 1 else ""
        # Guess quantization from tag
        q = None
        for token in tag.split("-"):
            if token.lower().startswith("q") and "_" in token:
                q = token
                break
        # Guess parameters from tag (e.g., "8b", "70b")
        params = None
        for token in tag.split("-"):
            low = token.lower()
            if low.endswith("b") and low[:-1].replace(".", "", 1).isdigit():
                params = token.upper()
                break
        models.append(
            ModelInfo(
                id=name,
                name=base_name,
                parameters=params,
                quantization=q,
            )
        )
    return models


def _parse_lmstudio_models(data: Dict[str, Any]) -> List[ModelInfo]:
    """ELI5: LM Studio hands us template cards in OpenAI-style format;
    this helper converts them to our standard recipe cards.
    """
    models: List[ModelInfo] = []
    raw_models = data.get("data", []) if isinstance(data, dict) else []
    for raw in raw_models:
        if not isinstance(raw, dict):
            continue
        mid = raw.get("id", "")
        models.append(ModelInfo(id=mid, name=mid))
    return models


# ──────────────────────────────────────────────────────────────────────────────
# IP Range Generator
# ──────────────────────────────────────────────────────────────────────────────

def _generate_targets(config: DiscoveryConfig) -> Set[str]:
    """ELI5: Build the patrol route — every room number (IP) the survey team
    should knock on, for both Ollama and LM Studio doors.
    """
    targets: Set[str] = set()

    for network in config.local_networks:
        try:
            net = ipaddress.ip_network(network, strict=False)
            for host in net.hosts():
                host_str = str(host)
                for port in config.ollama_ports:
                    targets.add(f"http://{host_str}:{port}")
                for port in config.lmstudio_ports:
                    targets.add(f"http://{host_str}:{port}")
            # Always include the network address itself (e.g., 127.0.0.1)
            if net.num_addresses == 1:
                host_str = str(net.network_address)
                for port in config.ollama_ports:
                    targets.add(f"http://{host_str}:{port}")
                for port in config.lmstudio_ports:
                    targets.add(f"http://{host_str}:{port}")
        except ValueError as exc:
            logger.warning("Bad network CIDR '%s': %s", network, exc)

    for host in config.extra_hosts:
        for port in config.ollama_ports:
            targets.add(f"http://{host}:{port}")
        for port in config.lmstudio_ports:
            targets.add(f"http://{host}:{port}")

    return targets


# ──────────────────────────────────────────────────────────────────────────────
# Discovery Daemon
# ──────────────────────────────────────────────────────────────────────────────

class DiscoveryDaemon:
    """ELI5: The night-shift survey crew boss. Runs the patrol schedule,
    interprets the team's radio reports, updates the master floor-plan,
    and blasts PA announcements.
    """

    def __init__(
        self,
        config: Optional[DiscoveryConfig] = None,
        catalog: Optional[EndpointCatalog] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.config = config or DiscoveryConfig()
        self.catalog = catalog or get_default_catalog()
        self.bus = event_bus or EventBus()
        self._task: Optional[asyncio.Task[None]] = None
        self._stop_event = asyncio.Event()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """ELI5: Punch the time-clock and send the crew out on their first round."""
        if self._task is not None and not self._task.done():
            logger.warning("Crew is already on patrol.")
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._patrol_loop())
        logger.info("DiscoveryDaemon started — patrol every %s s", self.config.scan_interval_seconds)

    async def stop(self) -> None:
        """ELI5: Blow the whistle — crew comes back to base."""
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("DiscoveryDaemon stopped.")

    # ── Patrol Loop ───────────────────────────────────────────────────────────

    async def _patrol_loop(self) -> None:
        """ELI5: The repeating patrol route — wait 30 s, then knock on every door."""
        while not self._stop_event.is_set():
            try:
                await self._run_survey_round()
            except Exception as exc:
                logger.exception("Survey round crashed: %s", exc)

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.config.scan_interval_seconds,
                )
            except TimeoutError:
                pass  # ELI5: 30 s are up — time for another round.

    async def _run_survey_round(self) -> None:
        """ELI5: One full lap around the building — knock, check, report."""
        targets = _generate_targets(self.config)
        logger.info("Starting survey round — %d doors to knock on", len(targets))

        sem = asyncio.Semaphore(20)  # ELI5: Only 20 surveyors knocking at once.

        async def _probe_one(target_url: str) -> None:
            async with sem:
                await self._probe_and_update(target_url)

        await asyncio.gather(*[_probe_one(url) for url in targets], return_exceptions=True)
        logger.info("Survey round complete.")

    async def _probe_and_update(self, url: str) -> None:
        """ELI5: One surveyor walks up to a single door, tries both
        Ollama-style and LM Studio-style handshakes, then radios the boss.
        """
        # ELI5: Try Ollama first (port 11434 is a dead giveaway).
        provider = self._guess_provider_from_url(url)
        report = await probe_endpoint(url, provider)

        if report.status == HealthStatus.OFFLINE:
            # ELI5: Nobody answered — maybe we guessed the wrong brand of door.
            other = "lmstudio" if provider == "ollama" else "ollama"
            report2 = await probe_endpoint(url, other)
            if report2.status != HealthStatus.OFFLINE:
                report = report2
                provider = other

        # ELI5: Fetch the full template list so the catalog is accurate.
        models: List[ModelInfo] = []
        if report.status != HealthStatus.OFFLINE:
            models = await self._fetch_models(url, provider)

        # ELI5: Map the inspector's sticker color to our catalog status.
        status_map = {
            HealthStatus.HEALTHY: EndpointStatus.HEALTHY,
            HealthStatus.DEGRADED: EndpointStatus.DEGRADED,
            HealthStatus.OFFLINE: EndpointStatus.OFFLINE,
        }

        # ELI5: Build the updated station dossier.
        endpoint = LLMEndpoint(
            url=url,
            provider=Provider.OLLAMA if provider == "ollama" else Provider.LMSTUDIO,
            models=models,
            status=status_map[report.status],
            latency_ms=report.latency_ms,
            last_seen=report.timestamp,
            gpu_utilization=report.gpu_info.utilization_percent if report.gpu_info else None,
            vram_free_mb=report.gpu_info.vram_free_mb if report.gpu_info else None,
        )

        # ELI5: Check if the sticker color changed so we can announce it.
        previous = await self.catalog.get(url)
        prev_status = previous.status if previous else None

        await self.catalog.upsert(endpoint)

        event_type = "upsert" if previous is None else "health_changed"
        await self.bus.publish(
            HealthEvent(
                event_type=event_type,
                endpoint=endpoint,
                previous_status=prev_status.value if prev_status else None,
            )
        )

        logger.debug("Updated %s — status=%s models=%d", url, endpoint.status, len(models))

    def _guess_provider_from_url(self, url: str) -> str:
        """ELI5: Look at the door number (port) to guess whether it's an
        Ollama station or an LM Studio station before we knock.
        """
        for port in self.config.ollama_ports:
            if f":{port}" in url:
                return "ollama"
        return "lmstudio"

    async def _fetch_models(self, url: str, provider: str) -> List[ModelInfo]:
        """ELI5: Ask the station for its full template catalog."""
        async with httpx.AsyncClient() as client:
            if provider == "ollama":
                probe_url = f"{url.rstrip('/')}/api/tags"
                try:
                    resp = await client.get(probe_url, timeout=self.config.probe_timeout_seconds)
                    if resp.status_code == 200:
                        return _parse_ollama_models(resp.json())
                except Exception as exc:
                    logger.debug("Failed to fetch Ollama models from %s: %s", url, exc)
            else:
                probe_url = f"{url.rstrip('/')}/v1/models"
                try:
                    resp = await client.get(probe_url, timeout=self.config.probe_timeout_seconds)
                    if resp.status_code == 200:
                        return _parse_lmstudio_models(resp.json())
                except Exception as exc:
                    logger.debug("Failed to fetch LM Studio models from %s: %s", url, exc)
        return []


# ──────────────────────────────────────────────────────────────────────────────
# Signal Handling & Entry Point
# ──────────────────────────────────────────────────────────────────────────────

async def _main() -> None:
    """ELI5: The night shift starts here. Set up the boss, start the patrol,
    and wait for the whistle (Ctrl+C) to end the shift.
    """
    config = DiscoveryConfig()
    daemon = DiscoveryDaemon(config=config)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(daemon.stop()))

    await daemon.start()

    # ELI5: Park the boss at a desk and wait for the end-of-shift whistle.
    try:
        while daemon._task is not None and not daemon._task.done():
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        pass
    finally:
        await daemon.stop()


if __name__ == "__main__":
    asyncio.run(_main())
