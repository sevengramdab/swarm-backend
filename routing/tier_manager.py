#!/usr/bin/env python3
"""
tier_manager.py
===============
Tier definitions and health monitoring.

ELI5 Analogy:
  Your house has three power sources:
  - Solar panels on the roof (local tier)
  - A backup generator in the garage (shadow tier)
  - The utility grid pole outside (cloud tier)
  TierManager keeps a directory of every source: how many amps
  it can deliver, whether the breaker is tripped, and how much
  it costs per kilowatt-hour.
"""

from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class TierConfig(BaseModel):
    """One power source in the directory."""

    name: str  # e.g. "local", "shadow", "cloud_rtx5090"
    display_name: str
    nodes: List[str] = Field(default_factory=list)
    models: List[str] = Field(default_factory=list)
    max_latency_ms: float = 5000.0
    cost_per_1k_tokens: float = 0.0
    health_status: HealthStatus = HealthStatus.HEALTHY
    health_reason: Optional[str] = None
    last_health_check: float = Field(default_factory=time.time)
    capacity_score: float = 1.0  # relative compute capacity
    enabled: bool = True


class TierManager:
    """
    The power source directory.

    ELI5: Like the main electrical service panel directory sticker
          inside the breaker box door. It lists every circuit,
          its amp rating, and which rooms it serves. If a circuit
          trips, the electrician crosses it out in red marker
          (degraded/offline) until it's fixed.
    """

    def __init__(self) -> None:
        self.tiers: Dict[str, TierConfig] = {}
        self._lock = asyncio.Lock()

    async def register_tier(self, config: TierConfig) -> None:
        """Add a new power source to the directory sticker."""
        async with self._lock:
            self.tiers[config.name] = config

    async def deregister_tier(self, name: str) -> bool:
        """Remove a power source (e.g., decommissioned solar array)."""
        async with self._lock:
            return self.tiers.pop(name, None) is not None

    async def update_health(
        self,
        name: str,
        status: HealthStatus,
        reason: Optional[str] = None,
    ) -> bool:
        """
        ELI5: The solar inverter just faulted. The homeowner updates
              the directory sticker: "SOLAR — OFFLINE — inverter fault
              until Tuesday." Now the automatic transfer switch knows
              not to route any load there.
        """
        async with self._lock:
            tier = self.tiers.get(name)
            if not tier:
                return False
            tier.health_status = status
            tier.health_reason = reason
            tier.last_health_check = time.time()
            return True

    async def get_healthy_tiers(self) -> List[TierConfig]:
        """Return only power sources that are currently online."""
        async with self._lock:
            return [
                t for t in self.tiers.values()
                if t.health_status == HealthStatus.HEALTHY and t.enabled
            ]

    async def get_all_tiers(self) -> List[TierConfig]:
        """Return every power source, even the broken ones."""
        async with self._lock:
            return list(self.tiers.values())

    async def get_tier(self, name: str) -> Optional[TierConfig]:
        """Look up one power source by its circuit label."""
        async with self._lock:
            return self.tiers.get(name)

    async def set_enabled(self, name: str, enabled: bool) -> bool:
        """Flip the disconnect switch for a whole tier."""
        async with self._lock:
            tier = self.tiers.get(name)
            if tier:
                tier.enabled = enabled
                return True
            return False

    def auto_degrade_stale(self, stale_seconds: float = 60.0) -> List[str]:
        """
        ELI5: If the solar panels haven't reported their voltage in
              over a minute, assume a wire fell off and mark them
              DEGRADED automatically.
        """
        now = time.time()
        degraded: List[str] = []
        for tier in self.tiers.values():
            if tier.health_status == HealthStatus.HEALTHY:
                if (now - tier.last_health_check) > stale_seconds:
                    tier.health_status = HealthStatus.DEGRADED
                    tier.health_reason = "stale health check"
                    degraded.append(tier.name)
        return degraded
