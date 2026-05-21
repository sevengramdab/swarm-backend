#!/usr/bin/env python3
"""
dependencies.py
===============
Shared FastAPI dependencies.

ELI5: Like the main utility closet in a building. Every electrician
      (API endpoint) grabs the same multimeter, wire strippers, and
      safety gloves (singleton services) from the same closet instead
      of carrying their own.
"""

from __future__ import annotations

from typing import Optional

# These are lazy imports / placeholders because the actual modules
# may not be importable until the full system is wired together.
# In production, replace with direct imports.

_swarm_orchestrator: Optional[object] = None
_main_breaker: Optional[object] = None
_telemetry_logger: Optional[object] = None
_discovery_daemon: Optional[object] = None
_endpoint_catalog: Optional[object] = None


def get_swarm_orchestrator() -> object:
    """
    ELI5: Grab the master panel key from the utility closet.
          Whoever holds this key can start or stop the whole building.

    Lazy-initializes a real MassAgentOrchestrator on first call
    so the API is never stuck in demo mode.
    """
    global _swarm_orchestrator
    if _swarm_orchestrator is None:
        from .settings_store import get_setting
        from swarm.orchestrator_bridge import OrchestratorBridge
        _swarm_orchestrator = OrchestratorBridge(
            max_agents=get_setting('swarm_max_agents', 10),
            initial_agents=get_setting('swarm_initial_agents', 3),
            task_timeout=get_setting('swarm_task_timeout_seconds', 30.0),
            auto_scale=get_setting('swarm_auto_scale', True),
        )
    return _swarm_orchestrator


def get_main_breaker() -> object:
    """
    ELI5: Grab the Main Breaker handle. This controls whether power
          flows from solar, generator, or grid for every new appliance.
    """
    if _main_breaker is None:
        from .settings_store import get_setting
        from routing.main_breaker import MainBreaker
        from routing.tier_manager import TierManager, TierConfig, HealthStatus
        from routing.load_balancer import LoadBalancer
        tm = TierManager()
        tiers = get_setting('tiers', [])
        import asyncio
        for t in tiers:
            asyncio.run(tm.register_tier(TierConfig(
                name=t['name'],
                display_name=t.get('display_name', t['name']),
                nodes=t.get('nodes', []),
                models=t.get('models', []),
                health_status=HealthStatus(t.get('health_status', 'healthy'))
            )))
        if not tiers:
            asyncio.run(tm.register_tier(TierConfig(name="local", display_name="Local", nodes=["local"], health_status=HealthStatus.HEALTHY)))
        return MainBreaker(tier_manager=tm, load_balancer=LoadBalancer(), threshold=get_setting('routing_default_threshold', 0.5))
    return _main_breaker


def get_telemetry_logger() -> object:
    """Grab the building's security camera DVR — every event gets recorded."""
    if _telemetry_logger is None:
        from .settings_store import get_setting
        from swarm.telemetry.telemetry_logger import TelemetryLogger
        return TelemetryLogger(output_dir=get_setting('telemetry_output_dir', 'telemetry_logs'))
    return _telemetry_logger


def get_discovery_daemon() -> object:
    """Grab the smart home hub that knows every connected device."""
    return _discovery_daemon


def get_endpoint_catalog() -> object:
    """Grab the directory of all known LLM endpoints."""
    return _endpoint_catalog


def init_dependencies(
    orchestrator: object,
    main_breaker: object,
    telemetry: object,
    discovery: object,
    catalog: object = None,
) -> None:
    """
    ELI5: Stock the utility closet on opening day.
          This runs once when the building first powers up.
    """
    global _swarm_orchestrator, _main_breaker, _telemetry_logger, _discovery_daemon, _endpoint_catalog
    _swarm_orchestrator = orchestrator
    _main_breaker = main_breaker
    _telemetry_logger = telemetry
    _discovery_daemon = discovery
    _endpoint_catalog = catalog
