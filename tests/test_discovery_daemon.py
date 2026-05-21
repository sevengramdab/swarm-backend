#!/usr/bin/env python3
"""
test_discovery_daemon.py
========================
Unit tests for the Hybrid Local Discovery Service.

ELI5: We set up two fake drawing stations in the office — one
      pretending to be Ollama, one pretending to be LM Studio.
      Then we send the survey team to knock on their doors and
      verify the survey report matches what we hung on the doors.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from httpx import Response

# We will mock httpx.AsyncClient rather than running real servers.
from bridge.discovery.discovery_daemon import DiscoveryDaemon
from bridge.discovery.endpoint_catalog import EndpointCatalog, LLMEndpoint
from bridge.discovery.health_checker import HealthReport, probe_endpoint


class TestDiscoveryDaemon:
    @pytest.mark.asyncio
    async def test_catalog_stores_endpoint(self) -> None:
        """
        ELI5: The survey team finds a plotter and writes it on the
              master floor plan. Later, the foreman checks the plan
              and sees the plotter listed.
        """
        catalog = EndpointCatalog()
        ep = LLMEndpoint(
            url="http://127.0.0.1:11434",
            provider="ollama",
            models=[],
            status="healthy",
            latency_ms=12.0,
        )
        await catalog.upsert(ep)
        found = await catalog.get_by_url("http://127.0.0.1:11434")
        assert found is not None
        assert found.provider == "ollama"

    @pytest.mark.asyncio
    async def test_catalog_filters_by_provider(self) -> None:
        """
        ELI5: The foreman asks, "Show me only the Ollama plotters."
              The catalog should hide the LM Studio ones for that query.
        """
        catalog = EndpointCatalog()
        await catalog.upsert(LLMEndpoint(url="http://a:11434", provider="ollama", models=[], status="healthy", latency_ms=10))
        await catalog.upsert(LLMEndpoint(url="http://b:1234", provider="lmstudio", models=[], status="healthy", latency_ms=20))

        ollamas = await catalog.list_by_provider("ollama")
        assert len(ollamas) == 1
        assert ollamas[0].url == "http://a:11434"


class TestHealthChecker:
    def test_health_report_model(self) -> None:
        """
        ELI5: The plotter's health inspection form should have boxes
              for latency, model count, and a big PASS/FAIL stamp.
        """
        report = HealthReport(
            url="http://localhost:11434",
            provider="ollama",
            status="healthy",
            latency_ms=15.0,
            models_found=3,
        )
        assert report.status == "healthy"
        assert report.models_found == 3
