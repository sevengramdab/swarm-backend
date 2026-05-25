"""
HARDWARE ROUTER v2.0 — Real-world aquaculture hardware integration
Endpoints for:
  - Receiving sensor data from ESP32 controllers
  - Multi-supplier BOM with build profiles
  - Build analysis engine (cost, thermal, ROI, risk)
  - Wiring schematics and documentation
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from core.orbstudio_hardware import (
    AquacultureSpec,
    HydroponicSpec,
    ThermalEngineering,
    WIRING_SCHEMATIC,
    ALL_ITEMS,
    ALL_PROFILES,
    get_manifest_with_selections,
    get_build_profiles,
    analyze_build,
    BuildProfile,
)

router = APIRouter(prefix="/hardware", tags=["hardware"])

# In-memory telemetry storage (last reading per controller)
_controller_telemetry: Dict[str, Dict[str, Any]] = {}


class TelemetryPayload(BaseModel):
    controller_id: str
    timestamp: int
    sensors: Dict[str, float]
    relays: Dict[str, bool]


class TelemetryResponse(BaseModel):
    received: bool
    controller_id: str
    sensor_count: int
    relay_count: int


class AnalyzeBuildRequest(BaseModel):
    profile_id: Optional[str] = None
    profile_name: Optional[str] = None
    custom_selections: Optional[Dict[str, int]] = None


# ─── TELEMETRY ENDPOINTS ───

@router.post("/telemetry", response_model=TelemetryResponse)
async def receive_telemetry(payload: TelemetryPayload) -> Dict[str, Any]:
    """Receive sensor data from an ESP32 tank controller."""
    _controller_telemetry[payload.controller_id] = payload.dict()
    return {
        "received": True,
        "controller_id": payload.controller_id,
        "sensor_count": len(payload.sensors),
        "relay_count": len(payload.relays),
    }


@router.get("/telemetry/{controller_id}")
async def get_telemetry(controller_id: str) -> Dict[str, Any]:
    """Get the latest telemetry from a specific controller."""
    data = _controller_telemetry.get(controller_id)
    if data is None:
        return {"error": f"No telemetry received from {controller_id} yet"}
    return data


@router.get("/telemetry")
async def get_all_telemetry() -> Dict[str, Any]:
    """Get all stored telemetry from all controllers."""
    return {
        "controller_count": len(_controller_telemetry),
        "controllers": list(_controller_telemetry.keys()),
        "readings": _controller_telemetry,
    }


# ─── BOM / MANIFEST ENDPOINTS (v2.0 with multi-supplier) ───

@router.get("/manifest")
async def get_hardware_manifest(selections: Optional[str] = None) -> Dict[str, Any]:
    """
    The full Bill of Materials with ALL supplier options per part.
    Optionally pass ?selections as JSON dict of {part_number: option_index}
    to see a customized build.
    """
    import json
    sel = {}
    if selections:
        try:
            sel = json.loads(selections)
        except Exception:
            pass
    return get_manifest_with_selections(sel)


@router.get("/manifest/item/{part_number}")
async def get_manifest_item(part_number: str) -> Dict[str, Any]:
    """Get one BOM item with all its supplier options."""
    for item in ALL_ITEMS:
        if item.part_number == part_number:
            return item.to_dict()
    return {"error": f"Item {part_number} not found"}


# ─── BUILD PROFILES ───

@router.get("/build-profiles")
async def get_profiles() -> Dict[str, Any]:
    """All pre-configured build profiles with cost summaries."""
    return {"profiles": get_build_profiles()}


@router.get("/build-profiles/{profile_id}")
async def get_profile_detail(profile_id: str) -> Dict[str, Any]:
    """Detailed breakdown of one build profile."""
    for p in ALL_PROFILES:
        if p.name.lower().replace(" ", "_") == profile_id:
            return {
                "id": profile_id,
                "name": p.name,
                "description": p.description,
                "icon": p.icon,
                "color": p.color,
                "strategy": p.strategy,
                "selections": p.item_selections,
                "detail": p.compute_total(),
            }
    return {"error": f"Profile {profile_id} not found"}


# ─── BUILD ANALYSIS ENGINE ───

@router.post("/analyze-build")
async def post_analyze_build(req: AnalyzeBuildRequest) -> Dict[str, Any]:
    """
    Analyze a build configuration and return a comprehensive engineering report.
    Pass profile_id to analyze a pre-defined profile, or custom_selections
    to analyze a custom configuration.
    """
    profile = None
    if req.profile_id:
        for p in ALL_PROFILES:
            if p.name.lower().replace(" ", "_") == req.profile_id:
                profile = p
                break
        if profile is None:
            return {"error": f"Profile {req.profile_id} not found"}
    elif req.profile_name:
        search = req.profile_name.lower()
        for p in ALL_PROFILES:
            if p.name.lower() == search or p.name.lower().replace(" build", "") == search or p.name.lower().replace(" local", "") == search:
                profile = p
                break
        if profile is None:
            return {"error": f"Profile {req.profile_name} not found"}
    elif req.custom_selections:
        profile = BuildProfile(
            name="Custom Build",
            description="User-customized sourcing configuration",
            icon="🔧",
            strategy="custom",
            color="purple",
            item_selections=req.custom_selections,
        )
    else:
        # Default to standard build
        profile = ALL_PROFILES[1]

    report = analyze_build(profile)
    return report.to_dict()


@router.get("/analyze-build/{profile_id}")
async def get_analyze_build(profile_id: str) -> Dict[str, Any]:
    """GET convenience endpoint for analyzing a pre-defined profile."""
    for p in ALL_PROFILES:
        if p.name.lower().replace(" ", "_") == profile_id:
            report = analyze_build(p)
            return report.to_dict()
    return {"error": f"Profile {profile_id} not found"}


# ─── AQUACULTURE & THERMAL ENDPOINTS ───

@router.get("/aquaculture-spec")
async def get_aquaculture_spec() -> Dict[str, Any]:
    """Real tilapia aquaculture parameters from FAO data."""
    spec = AquacultureSpec()
    return {
        "species": spec.species,
        "temperature": {
            "optimal_c": spec.optimal_temp_c,
            "stress_threshold_c": spec.stress_threshold_c,
            "cold_stress_c": spec.cold_stress_c,
            "lethal_max_c": spec.lethal_max_c,
            "lethal_min_c": spec.lethal_min_c,
        },
        "stocking_density": {
            "max_kg_per_m3": spec.max_density_kg_m3,
            "recommended_kg_per_m3": spec.recommended_density_kg_m3,
        },
        "water_quality": {
            "ph": {"optimal": spec.optimal_ph, "lethal": spec.lethal_ph},
            "dissolved_oxygen_mg_l": {
                "optimal": spec.optimal_do_mg_l,
                "minimum": spec.min_do_mg_l,
                "lethal": spec.lethal_do_mg_l,
            },
            "ammonia_mg_l": {"optimal": spec.optimal_nh3_mg_l, "maximum": spec.max_nh3_mg_l},
            "nitrite_mg_l": {"optimal": spec.optimal_no2_mg_l, "maximum": spec.max_no2_mg_l},
        },
        "feed": {
            "rate_pct_body_weight": spec.feed_rate_pct_body_weight,
            "protein_pct": spec.feed_protein_pct,
        },
        "growth": {
            "days_to_harvest": spec.days_to_harvest,
            "average_g_per_day": spec.growth_rate_g_day,
        },
    }


@router.get("/hydroponic-spec")
async def get_hydroponic_spec() -> Dict[str, Any]:
    """Real hydroponic parameters for DWC raft system paired with tilapia."""
    spec = HydroponicSpec()
    return {
        "system_type": spec.system_type,
        "temperature": {
            "optimal_c": spec.optimal_temp_c,
            "acceptable_range_c": spec.acceptable_temp_c,
        },
        "nutrients": {
            "ec_ms_per_cm": spec.ec_ms_cm,
            "ph_range": spec.ph,
        },
        "recommended_crops": spec.recommended_crops,
        "bed_specs": {
            "depth_cm": spec.bed_depth_cm,
            "plant_spacing_cm": spec.plant_spacing_cm,
            "biofilm_surface_area_m2_per_m3": spec.biofilm_surface_area_m2_m3,
        },
    }


@router.get("/thermal-engineering")
async def get_thermal_engineering() -> Dict[str, Any]:
    """Real heat transfer calculations for the server-to-aquaculture loop."""
    te = ThermalEngineering()
    earth_loss = te.earth_berm_loss_w()
    net_balance = te.heat_recovered_w - earth_loss - te.evap_cooling_w - te.makeup_cooling_w - te.grow_bed_heat_loss_w
    return {
        "server_heat_output": {
            "total_tdp_w": te.total_server_heat_w,
            "heat_recovered_via_hx_w": te.heat_recovered_w,
            "hx_efficiency": te.hex_efficiency,
        },
        "heat_exchanger": {
            "delta_t_c": 10.0,
            "glycol_inlet_c": 45.0,
            "glycol_outlet_c": 35.0,
            "water_inlet_c": 28.0,
            "water_outlet_c": 35.0,
        },
        "water_system": {
            "total_volume_l": te.total_water_volume_l,
            "specific_heat_j_kg_k": te.water_specific_heat_j_kg_k,
            "temp_rise_per_hour_c": te.temp_rise_per_hour_c,
        },
        "heat_losses": {
            "earth_berm_u_value": te.earth_berm_u_value,
            "tank_surface_area_m2": te.tank_surface_area_m2,
            "earth_loss_w": round(earth_loss, 1),
            "evaporative_cooling_w": te.evap_cooling_w,
            "makeup_water_cooling_w": te.makeup_cooling_w,
            "grow_bed_loss_w": te.grow_bed_heat_loss_w,
        },
        "net_balance_w": round(net_balance, 1),
        "recommendation": (
            "NET NEGATIVE — system will slowly cool. "
            "To maintain 28°C: insulate grow beds OR pre-heat return water through server exhaust OR reduce grow bed surface area."
        ),
    }


@router.get("/wiring-schematic", response_class=PlainTextResponse)
async def get_wiring_schematic() -> str:
    """The electrical submittal package — text-based wiring diagram."""
    return WIRING_SCHEMATIC
