"""
endpoint_catalog.py

ELI5: This is the master filing cabinet where we store the floor plans for every
      drawing station (LLM endpoint) in the building. Each drawer has a card
      (LLMEndpoint) listing the station's address, what templates (models) are
      loaded, and whether the plotter (GPU) has enough paper (VRAM).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────────────────────────────────────

class Provider(str, Enum):
    """ELI5: The brand of drafting table — Ollama or LM Studio."""
    OLLAMA = "ollama"
    LMSTUDIO = "lmstudio"


class EndpointStatus(str, Enum):
    """ELI5: Traffic-light sticker on each drawing station.
    
    green  = everything running smooth
    yellow = plotter jammed, running slow
    red    = station is dark, nobody home
    """
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class ModelInfo(BaseModel):
    """ELI5: A recipe card for one template (model) sitting in the plotter."""
    id: str = Field(..., description="Unique model identifier")
    name: str = Field(..., description="Human-readable model name")
    parameters: Optional[str] = Field(None, description="Parameter count, e.g. '7B'")
    context_length: Optional[int] = Field(None, description="Max context window")
    quantization: Optional[str] = Field(None, description="Quantization level, e.g. 'Q4_K_M'")
    gpu_required: Optional[bool] = Field(None, description="Whether GPU is recommended")


class LLMEndpoint(BaseModel):
    """ELI5: The full dossier for one drawing station in the office."""
    url: str = Field(..., description="Base URL of the endpoint")
    provider: Provider = Field(..., description="Backend provider type")
    models: List[ModelInfo] = Field(default_factory=list, description="Available models")
    status: EndpointStatus = Field(default=EndpointStatus.OFFLINE, description="Current health status")
    latency_ms: Optional[float] = Field(None, description="Last measured response time in ms")
    last_seen: Optional[datetime] = Field(None, description="Timestamp of last successful probe")
    gpu_utilization: Optional[float] = Field(None, description="GPU util % if available")
    vram_free_mb: Optional[float] = Field(None, description="Free VRAM in MB if available")

    def model_dump_json(self, **kwargs: Any) -> str:
        """ELI5: Xerox the dossier into a fax-friendly format (JSON string)."""
        return super().model_dump_json(**kwargs)


# ──────────────────────────────────────────────────────────────────────────────
# In-Memory Endpoint Catalog
# ──────────────────────────────────────────────────────────────────────────────

class EndpointCatalog:
    """ELI5: The head draftsman's clipboard. Keeps every station dossier handy,
    lets you flip to the ones with the right templates, and broadcasts updates
    over the office PA system (async callbacks) so the whole crew stays in sync.
    """

    def __init__(self) -> None:
        # ELI5: The actual filing cabinet — keyed by station address (URL).
        self._endpoints: Dict[str, LLMEndpoint] = {}
        # ELI5: PA-system subscriber list — anyone who wants to hear about updates.
        self._subscribers: List[Callable[[str, LLMEndpoint], asyncio.Future[None] | None]] = []
        self._lock = asyncio.Lock()

    # ── CRUD ──────────────────────────────────────────────────────────────────

    async def upsert(self, endpoint: LLMEndpoint) -> None:
        """ELI5: File a new dossier, or overwrite the old one if it exists."""
        async with self._lock:
            self._endpoints[endpoint.url] = endpoint
        await self._notify("upsert", endpoint)

    async def remove(self, url: str) -> Optional[LLMEndpoint]:
        """ELI5: Pull a dossier out of the cabinet and toss it in the shredder."""
        async with self._lock:
            removed = self._endpoints.pop(url, None)
        if removed:
            await self._notify("remove", removed)
        return removed

    async def get(self, url: str) -> Optional[LLMEndpoint]:
        """ELI5: Pull one dossier by its address label."""
        async with self._lock:
            return self._endpoints.get(url)

    async def list_all(self) -> List[LLMEndpoint]:
        """ELI5: Dump every dossier onto the conference table."""
        async with self._lock:
            return list(self._endpoints.values())

    async def clear(self) -> None:
        """ELI5: Empty the whole filing cabinet into the recycling bin."""
        async with self._lock:
            self._endpoints.clear()

    # ── Filtering ─────────────────────────────────────────────────────────────

    async def filter_by_provider(self, provider: Provider) -> List[LLMEndpoint]:
        """ELI5: Show me only the Ollama stations, or only the LM Studio ones."""
        async with self._lock:
            return [ep for ep in self._endpoints.values() if ep.provider == provider]

    async def filter_by_status(self, status: EndpointStatus) -> List[LLMEndpoint]:
        """ELI5: Show me only the stations with green stickers (or yellow/red)."""
        async with self._lock:
            return [ep for ep in self._endpoints.values() if ep.status == status]

    async def filter_by_capability(self, capability_filter: str) -> List[ModelInfo]:
        """ELI5: Which templates across the whole building match a keyword?
        
        capability_filter is matched against model id, name, and quantization.
        """
        matches: List[ModelInfo] = []
        async with self._lock:
            for ep in self._endpoints.values():
                for model in ep.models:
                    haystack = f"{model.id} {model.name} {model.quantization or ''}".lower()
                    if capability_filter.lower() in haystack:
                        matches.append(model)
        return matches

    async def get_models_on_endpoint(self, url: str) -> List[ModelInfo]:
        """ELI5: Peek inside one station and list every template in its plotter."""
        async with self._lock:
            ep = self._endpoints.get(url)
            return list(ep.models) if ep else []

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_json(self) -> str:
        """ELI5: Photocopy the entire cabinet into one big fax (JSON)."""
        return json.dumps(
            {url: ep.model_dump(mode="json") for url, ep in self._endpoints.items()},
            indent=2,
            default=str,
        )

    @classmethod
    def from_json(cls, raw: str) -> "EndpointCatalog":
        """ELI5: Rebuild the filing cabinet from a fax someone sent you."""
        catalog = cls()
        data: Dict[str, Any] = json.loads(raw)
        for url, payload in data.items():
            catalog._endpoints[url] = LLMEndpoint(**payload)
        return catalog

    # ── Event Bus ─────────────────────────────────────────────────────────────

    def subscribe(self, callback: Callable[[str, LLMEndpoint], asyncio.Future[None] | None]) -> None:
        """ELI5: Sign up for PA-system announcements about catalog changes."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[str, LLMEndpoint], asyncio.Future[None] | None]) -> None:
        """ELI5: Unsubscribe from the PA system."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    async def _notify(self, event: str, endpoint: LLMEndpoint) -> None:
        """ELI5: Hit the PA button and announce the update to every subscriber."""
        for cb in self._subscribers:
            try:
                result = cb(event, endpoint)
                if asyncio.isfuture(result) or asyncio.iscoroutine(result):
                    await result  # type: ignore[misc]
            except Exception:
                # ELI5: If one speaker is busted, don't kill the whole PA system.
                pass


# ──────────────────────────────────────────────────────────────────────────────
# Module-level singleton (optional convenience)
# ──────────────────────────────────────────────────────────────────────────────

_default_catalog: Optional[EndpointCatalog] = None


def get_default_catalog() -> EndpointCatalog:
    """ELI5: Grab the shared clipboard so you don't carry your own everywhere."""
    global _default_catalog
    if _default_catalog is None:
        _default_catalog = EndpointCatalog()
    return _default_catalog
