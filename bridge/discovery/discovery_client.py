"""
discovery_client.py

ELI5: This is the front-desk clerk who helps other crews find the right
      drawing station. Want a template with '70B' in the name? The clerk
      flips through the master catalog. Need the fastest station for a
      specific template? The clerk checks latency stickers and picks the
      green one with the lowest number. You can also ask the clerk to
      buzz you (async subscription) whenever the catalog changes.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable, List, Optional

from endpoint_catalog import EndpointCatalog, LLMEndpoint, ModelInfo


# ──────────────────────────────────────────────────────────────────────────────
# Public Query API
# ──────────────────────────────────────────────────────────────────────────────

async def get_available_models(
    catalog: EndpointCatalog,
    capability_filter: Optional[str] = None,
) -> List[ModelInfo]:
    """ELI5: Ask the clerk 'What templates do we have in the building?'
    
    Optionally narrow it down: 'Show me only the ones that say 70B'.
    """
    if capability_filter:
        return await catalog.filter_by_capability(capability_filter)

    models: List[ModelInfo] = []
    for ep in await catalog.list_all():
        models.extend(ep.models)
    return models


async def get_best_endpoint(
    catalog: EndpointCatalog,
    model_id: str,
    strategy: str = "lowest_latency",
) -> Optional[LLMEndpoint]:
    """ELI5: 'I need to use template X — which station should I walk to?'
    
    Strategies:
      - lowest_latency : pick the station with the smallest ping (green sticker).
      - most_vram      : pick the station with the most free plotter paper.
      - least_loaded   : pick the station with the fewest templates loaded.
    """
    candidates: List[LLMEndpoint] = []
    for ep in await catalog.list_all():
        # ELI5: Only consider stations that actually carry this template.
        if any(m.id == model_id or m.name == model_id for m in ep.models):
            candidates.append(ep)

    if not candidates:
        return None

    # ELI5: Sort the candidate stations by the chosen priority.
    if strategy == "lowest_latency":
        candidates.sort(
            key=lambda ep: (ep.latency_ms if ep.latency_ms is not None else float("inf"))
        )
    elif strategy == "most_vram":
        candidates.sort(
            key=lambda ep: (
                ep.vram_free_mb if ep.vram_free_mb is not None else -1
            ),
            reverse=True,
        )
    elif strategy == "least_loaded":
        candidates.sort(key=lambda ep: len(ep.models))
    else:
        # ELI5: Unknown strategy? Just use the first one in the pile.
        pass

    return candidates[0]


# ──────────────────────────────────────────────────────────────────────────────
# Async Subscription Context Manager
# ──────────────────────────────────────────────────────────────────────────────

class CatalogUpdateStream:
    """ELI5: A walkie-talkie channel that buzzes you every time the master
    catalog changes. You pick it up at the front desk, listen for a while,
    then hand it back when you're done.
    """

    def __init__(self, catalog: EndpointCatalog) -> None:
        self._catalog = catalog
        self._queue: asyncio.Queue[tuple[str, LLMEndpoint]] = asyncio.Queue()
        self._callback: Optional[Callable[[str, LLMEndpoint], None]] = None

    async def _on_event(self, event: str, endpoint: LLMEndpoint) -> None:
        """ELI5: Internal relay — PA announcement → walkie-talkie beep."""
        await self._queue.put((event, endpoint))

    async def __aenter__(self) -> "CatalogUpdateStream":
        """ELI5: Pick up the walkie-talkie and tune in."""
        self._callback = self._on_event
        self._catalog.subscribe(self._callback)  # type: ignore[arg-type]
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        """ELI5: Hand the walkie-talkie back to the front desk."""
        if self._callback:
            self._catalog.unsubscribe(self._callback)  # type: ignore[arg-type]
        self._callback = None

    def __aiter__(self) -> "CatalogUpdateStream":
        return self

    async def __anext__(self) -> tuple[str, LLMEndpoint]:
        """ELI5: Wait for the next buzz on the walkie-talkie."""
        item = await self._queue.get()
        return item


@asynccontextmanager
async def subscribe_catalog_updates(
    catalog: Optional[EndpointCatalog] = None,
) -> AsyncGenerator[CatalogUpdateStream, None]:
    """ELI5: Front-desk convenience wrapper — grab a walkie-talkie, use it,
    and automatically return it when you're done (even if you stormed out).
    """
    from endpoint_catalog import get_default_catalog

    cat = catalog or get_default_catalog()
    stream = CatalogUpdateStream(cat)
    async with stream:
        yield stream


# ──────────────────────────────────────────────────────────────────────────────
# CLI sanity-check
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    async def _demo() -> None:
        from endpoint_catalog import LLMEndpoint, ModelInfo, EndpointStatus, Provider

        # ELI5: Set up a fake catalog with two stations for the demo.
        catalog = EndpointCatalog()
        await catalog.upsert(
            LLMEndpoint(
                url="http://127.0.0.1:11434",
                provider=Provider.OLLAMA,
                models=[
                    ModelInfo(id="llama3", name="Llama 3", parameters="8B", quantization="Q4_K_M"),
                    ModelInfo(id="phi4", name="Phi-4", parameters="14B"),
                ],
                status=EndpointStatus.HEALTHY,
                latency_ms=45.0,
                vram_free_mb=4096.0,
            )
        )
        await catalog.upsert(
            LLMEndpoint(
                url="http://127.0.0.1:1234",
                provider=Provider.LMSTUDIO,
                models=[
                    ModelInfo(id="local-model", name="DeepSeek-R1", parameters="32B"),
                ],
                status=EndpointStatus.HEALTHY,
                latency_ms=12.0,
                vram_free_mb=8192.0,
            )
        )

        print("=== All models ===")
        for m in await get_available_models(catalog):
            print(f"  - {m.name} ({m.parameters})")

        print("\n=== Filtered '14B' ===")
        for m in await get_available_models(catalog, capability_filter="14B"):
            print(f"  - {m.name}")

        print("\n=== Best endpoint for 'llama3' (lowest_latency) ===")
        best = await get_best_endpoint(catalog, "llama3", strategy="lowest_latency")
        print(f"  → {best.url if best else 'None'}")

        print("\n=== Best endpoint for 'local-model' (most_vram) ===")
        best = await get_best_endpoint(catalog, "local-model", strategy="most_vram")
        print(f"  → {best.url if best else 'None'}")

        print("\n=== Subscribing to catalog updates for 5 s ===")
        async with subscribe_catalog_updates(catalog) as stream:
            # ELI5: Fire a fake update in the background so the stream has something to say.
            async def _inject() -> None:
                await asyncio.sleep(0.5)
                await catalog.upsert(
                    LLMEndpoint(
                        url="http://127.0.0.1:11434",
                        provider=Provider.OLLAMA,
                        models=[ModelInfo(id="llama3", name="Llama 3")],
                        latency_ms=30.0,
                    )
                )

            asyncio.create_task(_inject())
            try:
                async with asyncio.timeout(5.0):
                    async for event, ep in stream:
                        print(f"  [EVENT] {event}: {ep.url} (latency={ep.latency_ms} ms)")
            except TimeoutError:
                print("  (subscription timeout — handing walkie-talkie back)")

    asyncio.run(_demo())
