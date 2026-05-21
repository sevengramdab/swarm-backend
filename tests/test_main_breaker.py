#!/usr/bin/env python3
"""
test_main_breaker.py
====================
Unit tests for the Main Breaker routing logic.

ELI5: Before the city inspector signs off on the electrical panel,
      they flip every breaker, overload every circuit, and make sure
      the automatic transfer switch snaps to the right source.
"""

from __future__ import annotations

import pytest

from routing.complexity_scorer import ComplexityScorer, InferenceRequest
from routing.tier_manager import TierConfig, TierManager, HealthStatus
from routing.load_balancer import LoadBalancer, BalancingStrategy
from routing.main_breaker import MainBreaker, RoutingMode


@pytest.fixture
def scorer() -> ComplexityScorer:
    return ComplexityScorer()


@pytest.fixture
def tier_manager() -> TierManager:
    tm = TierManager()
    asyncio = __import__("asyncio")
    asyncio.run(tm.register_tier(TierConfig(
        name="local", display_name="Local GTX 1650",
        nodes=["local_01"], models=["llama3:8b"],
        cost_per_1k_tokens=0.0, capacity_score=1.0,
    )))
    asyncio.run(tm.register_tier(TierConfig(
        name="cloud", display_name="Cloud RTX 5090",
        nodes=["cloud_01"], models=["gpt-4o"],
        cost_per_1k_tokens=0.03, capacity_score=10.0,
    )))
    return tm


@pytest.fixture
def load_balancer() -> LoadBalancer:
    return LoadBalancer(strategy=BalancingStrategy.LEAST_CONNECTIONS)


class TestComplexityScorer:
    def test_simple_prompt_low_score(self, scorer: ComplexityScorer) -> None:
        req = InferenceRequest(prompt="hi", expected_output_tokens=50)
        score = scorer.score(req)
        assert score.overall < 0.3
        assert score.tier_recommendation == "local"

    def test_large_prompt_high_score(self, scorer: ComplexityScorer) -> None:
        req = InferenceRequest(prompt=" ".join(["word"] * 10_000), expected_output_tokens=4000)
        score = scorer.score(req)
        assert score.overall > 0.5

    def test_reasoning_bumps_score(self, scorer: ComplexityScorer) -> None:
        req = InferenceRequest(prompt="think step by step about quantum physics")
        score = scorer.score(req)
        assert score.reasoning_factor > 0.3


class TestMainBreaker:
    @pytest.mark.asyncio
    async def test_force_local_routes_local(self, tier_manager: TierManager, load_balancer: LoadBalancer) -> None:
        breaker = MainBreaker(tier_manager, load_balancer, threshold=0.5)
        await breaker.force_local()
        req = InferenceRequest(prompt="hello world")
        decision = await breaker.route(req)
        assert decision.tier == "local"

    @pytest.mark.asyncio
    async def test_force_cloud_routes_cloud(self, tier_manager: TierManager, load_balancer: LoadBalancer) -> None:
        breaker = MainBreaker(tier_manager, load_balancer, threshold=0.5)
        await breaker.force_cloud()
        req = InferenceRequest(prompt="hello world")
        decision = await breaker.route(req)
        assert decision.tier == "cloud"

    @pytest.mark.asyncio
    async def test_threshold_boundary(self, tier_manager: TierManager, load_balancer: LoadBalancer) -> None:
        breaker = MainBreaker(tier_manager, load_balancer, threshold=0.5)
        # Low complexity → local
        decision = await breaker.route(InferenceRequest(prompt="hi"))
        assert decision.tier == "local"
        # High complexity → cloud
        decision = await breaker.route(InferenceRequest(prompt=" ".join(["word"] * 10_000), expected_output_tokens=4000))
        assert decision.tier == "cloud"

    @pytest.mark.asyncio
    async def test_circuit_breaker_trips(self, tier_manager: TierManager, load_balancer: LoadBalancer) -> None:
        breaker = MainBreaker(tier_manager, load_balancer, threshold=0.5)
        # Trip the local tier
        await breaker.report_failure("local")
        await breaker.report_failure("local")
        await breaker.report_failure("local")
        await breaker.report_failure("local")
        await breaker.report_failure("local")
        assert breaker._circuit_breaker.is_tripped("local")
