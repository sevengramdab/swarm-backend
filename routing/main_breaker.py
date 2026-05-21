#!/usr/bin/env python3
"""
main_breaker.py
===============
Compute Routing — "The Main Breaker" Slider.

ELI5 Analogy:
  This IS the Main Breaker in your home's electrical panel.
  The slider decides how much load stays on your solar panels
  (local GTX 1650) vs. how much gets drawn from the grid
  (cloud RTX 5090). A small lamp (simple prompt) runs on solar.
  A welder (image generation) flips to grid power automatically.
  If the solar inverter fails, the whole house transfers to grid
  until repairs are done (circuit breaker pattern).
"""

from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .complexity_scorer import ComplexityScorer, ComplexityScore, InferenceRequest
from .tier_manager import TierConfig, TierManager, HealthStatus
from .load_balancer import LoadBalancer, BalancingStrategy


class RoutingMode(str, Enum):
    AUTO = "auto"
    FORCE_LOCAL = "force_local"
    FORCE_CLOUD = "force_cloud"


class RoutingDecision(BaseModel):
    """The electrician's work order after checking the panel."""

    request_id: str
    tier: str
    node_id: Optional[str] = None
    model: Optional[str] = None
    complexity: ComplexityScore
    reason: str
    estimated_cost: float = 0.0
    estimated_latency_ms: float = 0.0
    fallback_available: bool = True


class CircuitBreakerState:
    """
    Tracks failures per tier — like a GFCI that trips after 5 ground faults.

    ELI5: If the solar panels fault 5 times in a row, the GFCI trips
          and refuses to send any more load to solar until someone
          manually resets it (or the auto-reset timer expires).
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures: Dict[str, List[float]] = {}
        self.tripped: Dict[str, float] = {}  # tier -> trip timestamp

    def record_failure(self, tier: str) -> bool:
        """Record a fault. Returns True if the breaker should trip."""
        now = time.time()
        self.failures.setdefault(tier, []).append(now)
        # Clear old failures outside the recovery window.
        self.failures[tier] = [
            t for t in self.failures[tier] if (now - t) < self.recovery_timeout
        ]
        if len(self.failures[tier]) >= self.failure_threshold:
            self.tripped[tier] = now
            return True
        return False

    def record_success(self, tier: str) -> None:
        """A successful load clears one fault from memory."""
        if tier in self.failures and self.failures[tier]:
            self.failures[tier].pop(0)
        # If no failures remain, untrip.
        if not self.failures.get(tier):
            self.tripped.pop(tier, None)

    def is_tripped(self, tier: str) -> bool:
        """Is this circuit currently locked out?"""
        if tier not in self.tripped:
            return False
        # Auto-reset after recovery timeout.
        if (time.time() - self.tripped[tier]) > self.recovery_timeout:
            self.tripped.pop(tier, None)
            self.failures.pop(tier, None)
            return False
        return True


class MainBreaker:
    """
    The master electrical panel.

    ELI5: You walk into the utility room. On the wall is a huge
          panel with a big red slider labeled SOLAR <-> GRID.
          Next to it are three LED indicators:
          - GREEN = solar panels healthy
          - YELLOW = generator (shadow PC) running
          - RED = everything routed to utility grid
          The smart controller inside watches every appliance
          turn on and automatically moves the slider so your
          100A main never overloads.
    """

    def __init__(
        self,
        tier_manager: TierManager,
        load_balancer: LoadBalancer,
        threshold: float = 0.5,
        mode: RoutingMode = RoutingMode.AUTO,
    ) -> None:
        self.scorer = ComplexityScorer()
        self.tier_manager = tier_manager
        self.load_balancer = load_balancer
        self._threshold = threshold  # 0.0 = all local, 1.0 = all cloud
        self._mode = mode
        self._circuit_breaker = CircuitBreakerState()
        self._lock = asyncio.Lock()
        self._request_counter = 0

    @property
    def threshold(self) -> float:
        return self._threshold

    async def set_threshold(self, value: float) -> None:
        """
        ELI5: Move the big red slider. 0 = everything on solar.
              1.0 = everything on grid. 0.5 = balanced mix.
        """
        async with self._lock:
            self._threshold = max(0.0, min(1.0, value))
            self._mode = RoutingMode.AUTO

    async def force_local(self) -> None:
        """Lock the slider to SOLAR — all local processing."""
        async with self._lock:
            self._mode = RoutingMode.FORCE_LOCAL

    async def force_cloud(self) -> None:
        """Lock the slider to GRID — all cloud processing."""
        async with self._lock:
            self._mode = RoutingMode.FORCE_CLOUD

    async def auto_balance(self) -> None:
        """Unlock the slider — let the smart controller decide."""
        async with self._lock:
            self._mode = RoutingMode.AUTO

    async def route(self, request: InferenceRequest) -> RoutingDecision:
        """
        The core routing decision — like the automatic transfer switch.

        ELI5: The AC compressor just kicked on (inference request).
              The transfer switch checks:
              1. Is solar producing enough? (complexity score < threshold)
              2. Is the solar inverter tripped? (circuit breaker)
              3. Did the homeowner lock the slider to GRID? (force mode)
              Then it snaps the contactor to the right power source.
        """
        async with self._lock:
            self._request_counter += 1
            request_id = f"REQ-{self._request_counter:06d}"

        complexity = self.scorer.score(request)
        healthy_tiers = await self.tier_manager.get_healthy_tiers()

        # Build tier name lists for quick lookup.
        local_tiers = [t for t in healthy_tiers if t.name == "local"]
        shadow_tiers = [t for t in healthy_tiers if t.name == "shadow"]
        cloud_tiers = [t for t in healthy_tiers if t.name.startswith("cloud")]

        # MODE OVERRIDES — like the manual override switch on a transfer panel.
        if self._mode == RoutingMode.FORCE_LOCAL:
            tier = self._pick_tier(local_tiers, "local")
            reason = "manual override: FORCE_LOCAL"
        elif self._mode == RoutingMode.FORCE_CLOUD:
            tier = self._pick_tier(cloud_tiers, "cloud")
            reason = "manual override: FORCE_CLOUD"
        else:
            # AUTO mode — the smart controller decides.
            tier, reason = await self._auto_route(
                complexity, local_tiers, shadow_tiers, cloud_tiers
            )

        # If the chosen tier is tripped (circuit breaker), fallback.
        if tier and self._circuit_breaker.is_tripped(tier.name):
            fallback = self._find_fallback(tier.name, local_tiers, shadow_tiers, cloud_tiers)
            if fallback:
                reason += f" (breaker tripped on {tier.name}, fallback to {fallback.name})"
                tier = fallback

        # If everything failed, return a null route.
        if not tier:
            return RoutingDecision(
                request_id=request_id,
                tier="none",
                complexity=complexity,
                reason="no healthy tiers available",
                fallback_available=False,
            )

        # Load-balance within the chosen tier.
        node_id = await self.load_balancer.select_node(tier.nodes)
        model = request.model_hint or (tier.models[0] if tier.models else None)

        return RoutingDecision(
            request_id=request_id,
            tier=tier.name,
            node_id=node_id,
            model=model,
            complexity=complexity,
            reason=reason,
            estimated_cost=complexity.overall * tier.cost_per_1k_tokens,
            estimated_latency_ms=tier.max_latency_ms,
            fallback_available=bool(self._find_fallback(tier.name, local_tiers, shadow_tiers, cloud_tiers)),
        )

    async def _auto_route(
        self,
        complexity: ComplexityScore,
        local_tiers: List[TierConfig],
        shadow_tiers: List[TierConfig],
        cloud_tiers: List[TierConfig],
    ) -> tuple[Optional[TierConfig], str]:
        """
        ELI5: The smart controller reads the load and the threshold:
              - Score below threshold → try solar (local) first
              - Score above threshold → go straight to grid (cloud)
              - If solar is cloudy (degraded) → use the generator (shadow)
              - If grid is down (tripped) → stay on solar even if overloaded
        """
        score = complexity.overall
        tier_rec = complexity.tier_recommendation

        if score <= self._threshold:
            # Prefer local/solar.
            if local_tiers:
                return self._pick_tier(local_tiers, "local"), f"score {score:.2f} <= threshold {self._threshold:.2f}"
            if shadow_tiers:
                return self._pick_tier(shadow_tiers, "shadow"), "local unavailable, fallback to shadow"
            if cloud_tiers:
                return self._pick_tier(cloud_tiers, "cloud"), "local/shadow unavailable, fallback to cloud"
        else:
            # Prefer cloud/grid.
            if cloud_tiers:
                return self._pick_tier(cloud_tiers, "cloud"), f"score {score:.2f} > threshold {self._threshold:.2f}"
            if shadow_tiers:
                return self._pick_tier(shadow_tiers, "shadow"), "cloud unavailable, fallback to shadow"
            if local_tiers:
                return self._pick_tier(local_tiers, "local"), "cloud/shadow unavailable, fallback to local"

        return None, "no tiers available"

    def _pick_tier(self, tiers: List[TierConfig], default_name: str) -> Optional[TierConfig]:
        """Grab the first healthy tier in the list — like the first available circuit."""
        for t in tiers:
            if t.enabled and t.health_status == HealthStatus.HEALTHY:
                return t
        return None

    def _find_fallback(
        self,
        current_tier_name: str,
        local_tiers: List[TierConfig],
        shadow_tiers: List[TierConfig],
        cloud_tiers: List[TierConfig],
    ) -> Optional[TierConfig]:
        """
        ELI5: The AC tripped the solar breaker. The transfer switch
              looks for the next available source: generator, then grid.
        """
        candidates: List[TierConfig] = []
        if current_tier_name == "local":
            candidates = shadow_tiers + cloud_tiers
        elif current_tier_name.startswith("cloud"):
            candidates = shadow_tiers + local_tiers
        else:
            candidates = local_tiers + cloud_tiers

        for t in candidates:
            if t.enabled and t.health_status == HealthStatus.HEALTHY:
                if not self._circuit_breaker.is_tripped(t.name):
                    return t
        return None

    async def report_failure(self, tier_name: str) -> bool:
        """A circuit faulted — log it and maybe trip the breaker."""
        tripped = self._circuit_breaker.record_failure(tier_name)
        if tripped:
            await self.tier_manager.update_health(tier_name, HealthStatus.DEGRADED, "circuit breaker tripped")
        return tripped

    async def report_success(self, tier_name: str) -> None:
        """A circuit carried load successfully — clear one fault."""
        self._circuit_breaker.record_success(tier_name)
