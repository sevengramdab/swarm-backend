#!/usr/bin/env python3
"""
routers/telemetry.py
====================
Telemetry data endpoints.

ELI5: Like the security camera monitors in the guard shack.
      You can watch live footage (SSE stream), play back
      recordings (history), or ask for a summary report.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..dependencies import get_telemetry_logger
from ..models import TelemetryEvent, TelemetrySummary

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("/realtime")
async def realtime_telemetry(logger=Depends(get_telemetry_logger)) -> StreamingResponse:
    """
    ELI5: Live security camera feed. The guard sits and watches
          a continuous stream of events as they happen.
    """
    from ..settings_store import get_setting
    heartbeat = get_setting('telemetry_sse_heartbeat_seconds', 2)
    async def event_stream() -> AsyncIterator[str]:
        # Placeholder: yield dummy heartbeat until real telemetry bus is wired.
        while True:
            yield f"data: {{'type':'heartbeat','ts':{__import__('time').time()}}}\n\n"
            await asyncio.sleep(heartbeat)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/history")
async def telemetry_history(
    limit: int = None,
    event_type: str | None = None,
    logger=Depends(get_telemetry_logger),
) -> list:
    """Play back security camera recordings."""
    from ..settings_store import get_setting
    if limit is None:
        limit = get_setting('telemetry_history_limit', 100)
    # Placeholder until real logger is wired.
    return []


@router.get("/summary", response_model=TelemetrySummary)
async def telemetry_summary(logger=Depends(get_telemetry_logger)) -> TelemetrySummary:
    """Ask the guard for a daily incident report."""
    return TelemetrySummary(
        total_events=0,
        events_last_hour=0,
        top_agents=[],
        top_event_types=[],
    )


@router.get("/agents/{agent_id}")
async def agent_telemetry(agent_id: str, logger=Depends(get_telemetry_logger)) -> list:
    """Show only the cameras pointed at one worker."""
    return []
