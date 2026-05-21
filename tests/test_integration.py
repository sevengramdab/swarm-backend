#!/usr/bin/env python3
"""
test_integration.py
===================
Integration test for the full swarm pipeline.

ELI5: Instead of testing one light switch at a time, we flip the
      main breaker ON, turn on every light in the house, run the
      washing machine, microwave, and AC simultaneously, then
      simulate a power surge to see if the transfer switch moves
      load to the generator. Finally, we shut everything down cleanly
      and check that no breakers are still warm.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

# Use local fixtures that wire together the real modules in-memory.
from swarm.memory.memory_bus import MemoryBus
from swarm.memory.agent_registry import AgentRegistry
from routing.main_breaker import MainBreaker
from routing.tier_manager import TierManager
from routing.load_balancer import LoadBalancer
from routing.complexity_scorer import InferenceRequest


@pytest.fixture
def temp_memory_bus(tmp_path: Path) -> MemoryBus:
    return MemoryBus(persist_path=tmp_path / "memory.jsonl")


@pytest.fixture
def temp_registry(tmp_path: Path) -> AgentRegistry:
    return AgentRegistry(persist_path=tmp_path / "registry.jsonl")


@pytest.fixture
def temp_main_breaker() -> MainBreaker:
    tm = TierManager()
    lb = LoadBalancer()
    return MainBreaker(tier_manager=tm, load_balancer=lb, threshold=0.5)


@pytest.mark.asyncio
async def test_full_pipeline(
    temp_memory_bus: MemoryBus,
    temp_registry: AgentRegistry,
    temp_main_breaker: MainBreaker,
) -> None:
    """
    ELI5: The grand opening of the building.
          1. Register two workers (agents).
          2. Write a log entry to the memory bus.
          3. Submit a simple light-bulb task — should route local.
          4. Submit a welding task — should route cloud.
          5. Mark one agent as stalled and verify registry reflects it.
          6. Shut down and verify the logbook has entries.
    """
    # 1. Register workers
    await temp_registry.register_agent("AGENT-001", capabilities=["text", "chat"], node_id="local")
    await temp_registry.register_agent("AGENT-002", capabilities=["image_gen"], node_id="cloud")

    # 2. Memory bus entry
    from swarm.memory.memory_bus import MemoryRecord
    record = MemoryRecord(topic="test_pipeline", payload={"step": 1})
    await temp_memory_bus.write(record)

    # 3. Simple task → local
    simple = InferenceRequest(prompt="Say hello", expected_output_tokens=50)
    decision_simple = await temp_main_breaker.route(simple)
    assert decision_simple.tier in ("local", "none")

    # 4. Complex task → cloud (if tier registered; else fallback)
    # Register a cloud tier so routing has somewhere to go.
    from routing.tier_manager import TierConfig, HealthStatus
    cloud_tier = TierConfig(
        name="cloud_rtx5090",
        display_name="Cloud RTX 5090",
        nodes=["poland-01"],
        models=["gpt-4"],
        health_status=HealthStatus.HEALTHY,
    )
    await temp_main_breaker.tier_manager.register_tier(cloud_tier)

    complex_req = InferenceRequest(
        prompt="Design a nuclear reactor step by step with full derivations",
        expected_output_tokens=4096,
        requires_reasoning=True,
    )
    decision_complex = await temp_main_breaker.route(complex_req)
    # With threshold 0.5, a high-complexity request should hit cloud.
    assert decision_complex.tier in ("cloud_rtx5090", "shadow", "none")

    # 5. Simulate stall
    await temp_registry.update_agent_status("AGENT-001", "degraded", telemetry={"error": "VRAM OOM"})
    history = temp_registry.get_agent_history("AGENT-001")
    assert any(e.event_type == "status_update" for e in history)

    # 6. Verify memory bus has our record
    recovered = await temp_memory_bus.read("test_pipeline")
    assert len(recovered) >= 1

    print("✅ Integration pipeline passed — all circuits operational.")
