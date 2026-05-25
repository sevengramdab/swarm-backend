"""
ORBSTUDIO SWARM — AGENT-014 (Dashboard UI/UX) + AGENT-015 (Integrator)
CIRCUIT: Main Breaker Control API
ANALOGY: This router is the remote control panel for the breaker box.
         Every endpoint is a switch, dial, or meter on the panel.
TIMESTAMP: 2026-05-22_1135_PST
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# AGENT-015: Wire into the existing SimplePod circuit
from core.orbstudio_thermal import (
    ThermalOrchestrator,
    BreakerState,
    create_default_orbstudio,
)

router = APIRouter(prefix="/orbstudio", tags=["orbstudio"])

# ─── MAIN BREAKER PANEL — SINGLETON INSTANCE ───
# ELI5: There's only ONE breaker panel in the building.
#       All API calls manipulate this same physical panel.
_orchestrator: Optional[ThermalOrchestrator] = None


def get_orchestrator() -> ThermalOrchestrator:
    """
    ELI5: The master key to the electrical room.
          If the panel hasn't been installed yet, install the default one.
    """
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = create_default_orbstudio()
    return _orchestrator


# ─── PYDANTIC MODELS — CONTROL KNOB SETTINGS ───

class BreakerOverrideRequest(BaseModel):
    """ELI5: A work order for the electrician — flip this breaker to this state."""
    zone_id: str
    state: str  # "CLOSED" or "OPEN"


class RackLoadRequest(BaseModel):
    """ELI5: A dispatch order to the data center — set this rack to this load %."""
    rack_id: str
    load_pct: float  # 0.0 - 100.0


class ThresholdUpdateRequest(BaseModel):
    """ELI5: Replacing the safety sticker on the breaker panel with new amp ratings."""
    max_safe_water_temp_c: Optional[float] = None
    max_server_exhaust_c: Optional[float] = None
    min_water_temp_c: Optional[float] = None


class OrchestratorStatus(BaseModel):
    """ELI5: The full meter-reading report from the breaker panel."""
    running: bool
    tick_interval_s: float
    ambient_earth_temp_c: float
    max_safe_water_temp_c: float
    max_server_exhaust_c: float
    min_water_temp_c: float
    zone_count: int
    rack_count: int
    breaker_state: str


# ─── ENDPOINTS — SWITCHES AND METERS ───

@router.get("/status", response_model=OrchestratorStatus)
async def orbstudio_status() -> Dict[str, Any]:
    """
    ELI5: Read the status LED on the front of the breaker panel.
          Tells you if the system is live, how fast the clock ticks,
          and how many zones/racks are wired in.
    """
    panel = get_orchestrator()
    open_zones = [zid for zid, z in panel.zones.items() if z.breaker_state.name == "OPEN"]
    breaker_state = "OPEN" if open_zones else "CLOSED"
    return {
        "running": panel._task is not None and not panel._task.done(),
        "tick_interval_s": panel.tick_interval_s,
        "ambient_earth_temp_c": panel.ambient_earth_temp_c,
        "max_safe_water_temp_c": panel.max_safe_water_temp_c,
        "max_server_exhaust_c": panel.max_server_exhaust_c,
        "min_water_temp_c": panel.min_water_temp_c,
        "zone_count": len(panel.zones),
        "rack_count": len(panel.racks),
        "breaker_state": breaker_state,
    }


@router.post("/start")
async def orbstudio_start() -> Dict[str, str]:
    """
    ELI5: CLOSE the Main Breaker — energize all circuits.
          The clock generator starts ticking.
    """
    panel = get_orchestrator()
    panel.start()
    return {"message": "Main Breaker CLOSED — circuits energized", "status": "running"}


@router.post("/stop")
async def orbstudio_stop() -> Dict[str, str]:
    """
    ELI5: OPEN the Main Breaker — emergency shutdown.
          All relays go dark. Clock generator stops.
    """
    panel = get_orchestrator()
    panel.stop()
    return {"message": "Main Breaker OPEN — emergency shutdown", "status": "stopped"}


@router.post("/shutdown")
async def orbstudio_shutdown() -> Dict[str, str]:
    """
    ELI5: Pull the master plug — shut down the entire backend server.
          Use this when you're done for the day.
    """
    import os, signal
    panel = get_orchestrator()
    panel.stop()
    # Schedule self-termination after response is sent
    def _kill():
        import time
        time.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)
    import threading
    threading.Thread(target=_kill, daemon=True).start()
    return {"message": "Server shutdown initiated. Goodbye.", "status": "shutting_down"}


@router.get("/snapshot")
async def orbstudio_snapshot() -> Dict[str, Any]:
    """
    ELI5: Take a digital photograph of the entire breaker panel.
          Every meter, every breaker position, every wire temperature.
          This is what the Dashboard UI renders as its Viewport.
    """
    panel = get_orchestrator()
    return panel.get_model_space_snapshot()


@router.post("/breaker/override")
async def orbstudio_breaker_override(req: BreakerOverrideRequest) -> Dict[str, str]:
    """
    ELI5: The maintenance electrician manually flips a breaker.
          Bypasses all automatic thermal logic.
          Use with caution — this is a manual override!
    """
    panel = get_orchestrator()
    if req.zone_id not in panel.zones:
        raise HTTPException(status_code=404, detail=f"Zone '{req.zone_id}' not found in Model Space")

    state = BreakerState.CLOSED if req.state.upper() == "CLOSED" else BreakerState.OPEN
    panel.manual_override(req.zone_id, state)
    return {
        "message": f"Breaker override applied to {req.zone_id}",
        "zone_id": req.zone_id,
        "state": state.name,
    }


@router.post("/rack/load")
async def orbstudio_rack_load(req: RackLoadRequest) -> Dict[str, Any]:
    """
    ELI5: Dispatch a load order to a specific compute rack.
          Like turning the dimmer switch on one circuit.
    """
    panel = get_orchestrator()
    if req.rack_id not in panel.racks:
        raise HTTPException(status_code=404, detail=f"Rack '{req.rack_id}' not found in Model Space")

    rack = panel.racks[req.rack_id]
    rack.current_load_pct = max(0.0, min(100.0, req.load_pct))
    return {
        "message": f"Rack {req.rack_id} load updated",
        "rack_id": req.rack_id,
        "current_load_pct": rack.current_load_pct,
        "actual_heat_output_w": round(rack.actual_heat_output_w, 1),
    }


@router.post("/thresholds")
async def orbstudio_thresholds(req: ThresholdUpdateRequest) -> Dict[str, Any]:
    """
    ELI5: Replace the safety ratings on the breaker panel.
          New amp ratings = new temperature limits.
    """
    panel = get_orchestrator()
    updated = {}
    if req.max_safe_water_temp_c is not None:
        panel.max_safe_water_temp_c = req.max_safe_water_temp_c
        updated["max_safe_water_temp_c"] = panel.max_safe_water_temp_c
    if req.max_server_exhaust_c is not None:
        panel.max_server_exhaust_c = req.max_server_exhaust_c
        updated["max_server_exhaust_c"] = panel.max_server_exhaust_c
    if req.min_water_temp_c is not None:
        panel.min_water_temp_c = req.min_water_temp_c
        updated["min_water_temp_c"] = panel.min_water_temp_c

    return {"message": "Breaker panel safety ratings updated", "updated": updated}


@router.get("/zones")
async def orbstudio_zones() -> Dict[str, Any]:
    """ELI5: Read all the thermometers in every tank and grow bed."""
    panel = get_orchestrator()
    return {
        zid: {
            "current_temp_c": round(z.current_temp_c, 2),
            "target_temp_c": z.target_temp_c,
            "thermal_mass_kg": z.thermal_mass_kg,
            "breaker_state": z.breaker_state.name,
        }
        for zid, z in panel.zones.items()
    }


@router.get("/racks")
async def orbstudio_racks() -> Dict[str, Any]:
    """ELI5: Read all the ammeters on every server rack circuit."""
    panel = get_orchestrator()
    return {
        rid: {
            "max_tdp_w": r.max_tdp_w,
            "current_load_pct": round(r.current_load_pct, 1),
            "throttle_pct": round(r.throttle_pct, 1),
            "is_online": r.is_online,
            "actual_heat_output_w": round(r.actual_heat_output_w, 1),
        }
        for rid, r in panel.racks.items()
    }


@router.get("/zones/{zone_id}/history")
async def orbstudio_zone_history(zone_id: str, limit: int = 100) -> Dict[str, Any]:
    """ELI5: Pull the chart recorder tape for one specific tank."""
    panel = get_orchestrator()
    if zone_id not in panel.zones:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")
    zone = panel.zones[zone_id]
    history = zone.history[-limit:] if zone.history else []
    return {
        "zone_id": zone_id,
        "record_count": len(history),
        "records": history,
    }
