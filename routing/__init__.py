"""
routing — Compute Routing ("The Main Breaker" Slider)

The multi-tier routing gateway that decides whether a request
stays on your home solar panels (local GTX 1650) or draws
from the grid (cloud RTX 5090).
"""

from .main_breaker import MainBreaker, RoutingDecision
from .complexity_scorer import ComplexityScorer, ComplexityScore
from .tier_manager import TierManager, TierConfig
from .load_balancer import LoadBalancer, BalancingStrategy

__all__ = [
    "MainBreaker",
    "RoutingDecision",
    "ComplexityScorer",
    "ComplexityScore",
    "TierManager",
    "TierConfig",
    "LoadBalancer",
    "BalancingStrategy",
]
