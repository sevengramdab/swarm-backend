#!/usr/bin/env python3
"""
load_balancer.py
================
Intra-tier load balancing.

ELI5 Analogy:
  You have three identical 20A circuits in the kitchen.
  When the microwave, toaster, and coffee maker all turn on,
  the load balancer is the smart panel that puts the microwave
  on Circuit A, the toaster on Circuit B, and the coffee maker
  on Circuit C — so no single breaker trips.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel


class BalancingStrategy(str, Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    LOWEST_LATENCY = "lowest_latency"
    WEIGHTED_CAPACITY = "weighted_capacity"


class NodeMetrics(BaseModel):
    """Real-time readings from one circuit breaker."""

    node_id: str
    active_tasks: int = 0
    latency_ms: float = 0.0
    capacity_score: float = 1.0
    last_seen: float = 0.0


class LoadBalancer:
    """
    The smart panel distributing load across parallel circuits.

    ELI5: Like a home automation load-shedding controller.
          It watches every smart breaker (node), knows how many
          amps each is already carrying (active_tasks), and picks
          the one with the most headroom for the next appliance.
    """

    def __init__(self, strategy: BalancingStrategy = BalancingStrategy.LEAST_CONNECTIONS) -> None:
        self.strategy = strategy
        self._node_metrics: Dict[str, NodeMetrics] = {}
        self._rr_index: int = 0
        self._lock = asyncio.Lock()
        self._sticky_sessions: Dict[str, str] = {}  # session_id -> node_id

    async def update_metrics(self, metrics: NodeMetrics) -> None:
        """Feed fresh breaker readings into the panel."""
        async with self._lock:
            self._node_metrics[metrics.node_id] = metrics

    async def remove_node(self, node_id: str) -> None:
        """A breaker was removed from the panel — clear its readings."""
        async with self._lock:
            self._node_metrics.pop(node_id, None)
            # Clean up sticky sessions pointing to dead nodes.
            dead_sessions = [s for s, n in self._sticky_sessions.items() if n == node_id]
            for s in dead_sessions:
                self._sticky_sessions.pop(s, None)

    async def select_node(
        self,
        candidates: List[str],
        session_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        ELI5: The homeowner plugs in a space heater.
              The smart panel looks at all available circuits,
              picks the best one based on the chosen strategy,
              and remembers which circuit this heater is on
              (sticky session) so it doesn't hop around.
        """
        async with self._lock:
            if not candidates:
                return None

            # Sticky session: if this heater was already on a circuit, keep it there.
            if session_id and session_id in self._sticky_sessions:
                sticky = self._sticky_sessions[session_id]
                if sticky in candidates:
                    return sticky

            # Filter to candidates we actually have metrics for.
            viable = [c for c in candidates if c in self._node_metrics]
            if not viable:
                # No metrics yet — just pick randomly like a dumb panel.
                choice = random.choice(candidates)
                if session_id:
                    self._sticky_sessions[session_id] = choice
                return choice

            if self.strategy == BalancingStrategy.ROUND_ROBIN:
                choice = self._round_robin(viable)
            elif self.strategy == BalancingStrategy.LEAST_CONNECTIONS:
                choice = self._least_connections(viable)
            elif self.strategy == BalancingStrategy.LOWEST_LATENCY:
                choice = self._lowest_latency(viable)
            elif self.strategy == BalancingStrategy.WEIGHTED_CAPACITY:
                choice = self._weighted_capacity(viable)
            else:
                choice = random.choice(viable)

            if session_id:
                self._sticky_sessions[session_id] = choice
            return choice

    def _round_robin(self, viable: List[str]) -> str:
        """Rotate through circuits A, B, C, A, B, C..."""
        self._rr_index = (self._rr_index + 1) % len(viable)
        return viable[self._rr_index]

    def _least_connections(self, viable: List[str]) -> str:
        """Pick the breaker carrying the fewest active loads."""
        return min(
            viable,
            key=lambda nid: self._node_metrics[nid].active_tasks,
        )

    def _lowest_latency(self, viable: List[str]) -> str:
        """Pick the breaker with the fastest response time."""
        return min(
            viable,
            key=lambda nid: self._node_metrics[nid].latency_ms,
        )

    def _weighted_capacity(self, viable: List[str]) -> str:
        """
        ELI5: Circuit A is 20A, Circuit B is 15A, Circuit C is 20A.
              We give the 20A circuits more chances to be picked
              because they can handle bigger loads.
        """
        weights = [self._node_metrics[nid].capacity_score for nid in viable]
        total = sum(weights)
        if total == 0:
            return random.choice(viable)
        pick = random.uniform(0, total)
        cumulative = 0.0
        for nid, w in zip(viable, weights):
            cumulative += w
            if cumulative >= pick:
                return nid
        return viable[-1]

    async def set_strategy(self, strategy: BalancingStrategy) -> None:
        """Change the panel's load-balancing algorithm."""
        async with self._lock:
            self.strategy = strategy
