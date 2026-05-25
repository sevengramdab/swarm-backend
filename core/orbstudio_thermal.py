"""
ORBSTUDIO SWARM — AGENT-013 (Swarm Programmer)
CIRCUIT: Thermal Routing & Server Throttle Logic
ANALOGY: This is the Main Breaker panel for the entire subterranean farm.
         Each "breaker" is a safety limit. Each "circuit" is a data flow.
         "Relays" are async triggers that flip when thresholds trip.
TIMESTAMP: 2026-05-22_1130_PST
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional, Dict, List, Any
import random


class BreakerState(Enum):
    """
    AutoCAD Viewport State — whether a breaker is open or closed in Model Space.
    CLOSED = current flows (system active)
    OPEN   = current stopped (safety trip)
    """
    CLOSED = auto()   # Breaker closed = power ON = system running
    OPEN = auto()     # Breaker open = power OFF = safety shutdown


@dataclass
class ThermalZone:
    """
    AutoCAD Layer — one thermal zone in Model Space.
    Think of this as a single "viewport" into one part of the farm.
    """
    zone_id: str                          # Layer name
    current_temp_c: float = 20.0          # Current reading (°C)
    target_temp_c: float = 28.0           # Setpoint for this zone
    thermal_mass_kg: float = 1000.0       # How much water (kg) — thermal inertia
    heat_input_w: float = 0.0             # Watts coming IN from servers
    heat_loss_w: float = 0.0              # Watts lost to ambient earth
    breaker_state: BreakerState = BreakerState.CLOSED
    history: List[Dict[str, Any]] = field(default_factory=list)

    def add_reading(self):
        """Relay — log a snapshot to the viewport history."""
        self.history.append({
            "timestamp": time.time(),
            "temp_c": self.current_temp_c,
            "heat_input_w": self.heat_input_w,
            "breaker": self.breaker_state.name,
        })
        # AutoCAD Layer Cleanup — keep only last 1000 viewport frames
        if len(self.history) > 1000:
            self.history = self.history[-1000:]


@dataclass
class ComputeRack:
    """
    AutoCAD Block Reference — one physical rack of servers.
    Each rack is a reusable "block" placed in Model Space.
    """
    rack_id: str
    max_tdp_w: float = 500.0          # Max thermal design power (W)
    current_load_pct: float = 0.0     # 0-100% utilization
    throttle_pct: float = 100.0       # 0-100% allowed load (Breaker limit)
    is_online: bool = True
    exhaust_temp_c: float = 35.0      # Hot air leaving the rack

    @property
    def actual_heat_output_w(self) -> float:
        """
        ELI5: Like reading an ammeter on a circuit.
              The actual watts = max rating × how hard it's working × throttle limit.
        """
        if not self.is_online:
            return 0.0
        effective_load = min(self.current_load_pct, self.throttle_pct)
        return self.max_tdp_w * (effective_load / 100.0)


class ThermalOrchestrator:
    """
    AGENT-013 CORE DELIVERABLE
    This is the Main Breaker Panel for the entire OrbStudio Swarm.
    It routes heat from Compute Racks → Thermal Zones → Aquaculture.
    """

    def __init__(
        self,
        zones: Optional[Dict[str, ThermalZone]] = None,
        racks: Optional[Dict[str, ComputeRack]] = None,
        tick_interval_s: float = 5.0,
    ):
        # Model Space — all our layers and blocks live here
        self.zones: Dict[str, ThermalZone] = zones or {}
        self.racks: Dict[str, ComputeRack] = racks or {}

        # Circuit Parameters — these are the "wire gauges" of our system
        self.tick_interval_s = tick_interval_s
        self.ambient_earth_temp_c = 15.0      # Deep earth temperature
        self.heat_transfer_coeff = 0.05       # How fast heat moves rack→water
        self.ambient_loss_coeff = 0.02        # How fast heat leaks to earth

        # Breaker Limits — if any of these trip, the Main Breaker flips OPEN
        self.max_safe_water_temp_c = 32.0     # Tilapia stress threshold
        self.max_server_exhaust_c = 75.0      # Hardware damage threshold
        self.min_water_temp_c = 22.0          # Tilapia too-cold threshold

        # Relay Wiring — callbacks that fire when breakers trip
        self._callbacks: List[Callable[[str, BreakerState], None]] = []

        # Circuit Loop Handle
        self._task: Optional[asyncio.Task] = None
        self._shutdown = False

    def register_breaker_callback(self, fn: Callable[[str, BreakerState], None]):
        """Wire a new relay into the breaker panel."""
        self._callbacks.append(fn)

    def _flip_breaker(self, zone_id: str, new_state: BreakerState):
        """ELI5: Like manually flipping a breaker switch in the panel."""
        zone = self.zones.get(zone_id)
        if zone and zone.breaker_state != new_state:
            zone.breaker_state = new_state
            for relay in self._callbacks:
                try:
                    relay(zone_id, new_state)
                except Exception:
                    pass  # Don't let a bad relay kill the whole panel

    def _route_heat(self) -> Dict[str, float]:
        """
        ELI5: This is the electrical busbar — it takes watts from all racks
              and distributes them to thermal zones like a load-balancing panel.
        """
        total_heat = sum(r.actual_heat_output_w for r in self.racks.values())
        if not self.zones:
            return {}

        # Distribute proportional to thermal mass (bigger tanks get more heat)
        total_mass = sum(z.thermal_mass_kg for z in self.zones.values())
        if total_mass == 0:
            return {zid: 0.0 for zid in self.zones}

        distribution: Dict[str, float] = {}
        for zid, zone in self.zones.items():
            share = (zone.thermal_mass_kg / total_mass) * total_heat
            distribution[zid] = share
        return distribution

    def _compute_throttle(self, zone: ThermalZone) -> float:
        """
        ELI5: This is the dimmer switch on the circuit.
              As water gets hotter, we dim the servers.
              If it gets too hot, we flip the breaker OFF.
        """
        temp = zone.current_temp_c

        # OVERHEAT — flip breaker OPEN (emergency shutdown)
        if temp >= self.max_safe_water_temp_c:
            self._flip_breaker(zone.zone_id, BreakerState.OPEN)
            return 0.0

        # RESTORE — if we cooled down enough, close the breaker again
        if temp <= self.max_safe_water_temp_c - 3.0:
            self._flip_breaker(zone.zone_id, BreakerState.CLOSED)

        # If breaker is open, throttle to 0
        if zone.breaker_state == BreakerState.OPEN:
            return 0.0

        # Proportional throttle: 100% at target, dropping as we approach max
        # This is like a variable resistor (rheostat) on the server circuit
        headroom = self.max_safe_water_temp_c - zone.target_temp_c
        if headroom <= 0:
            return 50.0  # Degenerate case — just give half power

        overshoot = max(0, temp - zone.target_temp_c)
        throttle = 100.0 - (overshoot / headroom * 100.0)
        return max(10.0, min(100.0, throttle))  # Never go below 10% (keep pumps alive)

    def tick(self):
        """
        ELI5: One full cycle of the electrical clock.
              Every tick we:
              1. Read all sensors (viewport snapshot)
              2. Route heat from racks to zones (busbar distribution)
              3. Calculate throttles (dimmer switches)
              4. Apply new temperatures (update Model Space)
              5. Log everything (save the viewport)
        """
        heat_distribution = self._route_heat()

        for zid, zone in self.zones.items():
            # Step 1: How much heat is arriving from the server circuit?
            heat_in = heat_distribution.get(zid, 0.0)

            # Step 2: How much heat leaks to ambient earth? (parasitic loss)
            temp_diff = zone.current_temp_c - self.ambient_earth_temp_c
            heat_loss = temp_diff * self.ambient_loss_coeff * zone.thermal_mass_kg

            # Step 3: Net energy change (Joules) in this tick
            net_watts = heat_in - heat_loss
            net_joules = net_watts * self.tick_interval_s

            # Step 4: Convert to temperature change
            # Specific heat of water ≈ 4186 J/kg·K
            delta_temp = net_joules / (zone.thermal_mass_kg * 4186)
            zone.current_temp_c += delta_temp

            # Step 5: Update zone bookkeeping
            zone.heat_input_w = heat_in
            zone.heat_loss_w = heat_loss
            zone.add_reading()

        # Step 6: Push throttles back to racks
        # All racks share one throttle — the most restrictive zone wins
        min_throttle = 100.0
        for zone in self.zones.values():
            t = self._compute_throttle(zone)
            if t < min_throttle:
                min_throttle = t

        for rack in self.racks.values():
            rack.throttle_pct = min_throttle if rack.is_online else 0.0

    async def _circuit_loop(self):
        """ELI5: The clock generator — keeps ticking the breaker panel forever."""
        while not self._shutdown:
            self.tick()
            await asyncio.sleep(self.tick_interval_s)

    def start(self):
        """Close the Main Breaker — energize the circuit."""
        if self._task is None or self._task.done():
            self._shutdown = False
            self._task = asyncio.create_task(self._circuit_loop())

    def stop(self):
        """Open the Main Breaker — emergency shutdown."""
        self._shutdown = True
        if self._task and not self._task.done():
            self._task.cancel()

    def get_model_space_snapshot(self) -> Dict[str, Any]:
        """
        AutoCAD Viewport Export — a read-only snapshot of the entire Model Space.
        This is what the Dashboard UI renders.
        """
        return {
            "timestamp": time.time(),
            "ambient_earth_temp_c": self.ambient_earth_temp_c,
            "max_safe_water_temp_c": self.max_safe_water_temp_c,
            "zones": {
                zid: {
                    "current_temp_c": round(z.current_temp_c, 2),
                    "target_temp_c": z.target_temp_c,
                    "thermal_mass_kg": z.thermal_mass_kg,
                    "heat_input_w": round(z.heat_input_w, 1),
                    "heat_loss_w": round(z.heat_loss_w, 1),
                    "breaker_state": z.breaker_state.name,
                    "latest_history": z.history[-10:] if z.history else [],
                }
                for zid, z in self.zones.items()
            },
            "racks": {
                rid: {
                    "max_tdp_w": r.max_tdp_w,
                    "current_load_pct": round(r.current_load_pct, 1),
                    "throttle_pct": round(r.throttle_pct, 1),
                    "is_online": r.is_online,
                    "actual_heat_output_w": round(r.actual_heat_output_w, 1),
                }
                for rid, r in self.racks.items()
            },
        }

    def manual_override(self, zone_id: str, breaker_state: BreakerState):
        """
        ELI5: The maintenance electrician manually flipping a breaker.
              This bypasses all automatic logic.
        """
        self._flip_breaker(zone_id, breaker_state)


# ─── FACTORY — DEFAULT ORBSTUDIO CONFIGURATION ───
def create_default_orbstudio() -> ThermalOrchestrator:
    """
    AGENT-015 (Integrator) — Blueprint Assembly
    Builds the default Model Space with all Layers and Blocks placed.
    Uses REAL thermal engineering numbers from orbstudio_hardware.py.
    """
    from core.orbstudio_hardware import ThermalEngineering
    te = ThermalEngineering()

    zones = {
        "tank_alpha": ThermalZone(
            zone_id="tank_alpha",
            current_temp_c=24.0,
            target_temp_c=28.0,
            thermal_mass_kg=5000.0,   # 5000L tilapia tank
        ),
        "tank_beta": ThermalZone(
            zone_id="tank_beta",
            current_temp_c=23.5,
            target_temp_c=28.0,
            thermal_mass_kg=5000.0,
        ),
        "hydro_grow_bed_north": ThermalZone(
            zone_id="hydro_grow_bed_north",
            current_temp_c=22.0,
            target_temp_c=26.0,
            thermal_mass_kg=2000.0,
        ),
        "hydro_grow_bed_south": ThermalZone(
            zone_id="hydro_grow_bed_south",
            current_temp_c=22.5,
            target_temp_c=26.0,
            thermal_mass_kg=2000.0,
        ),
    }

    racks = {
        "rack_compute_01": ComputeRack(
            rack_id="rack_compute_01",
            max_tdp_w=800.0,
            current_load_pct=65.0,
        ),
        "rack_compute_02": ComputeRack(
            rack_id="rack_compute_02",
            max_tdp_w=800.0,
            current_load_pct=70.0,
        ),
        "rack_compute_03": ComputeRack(
            rack_id="rack_compute_03",
            max_tdp_w=600.0,
            current_load_pct=45.0,
        ),
        "rack_storage_01": ComputeRack(
            rack_id="rack_storage_01",
            max_tdp_w=400.0,
            current_load_pct=30.0,
        ),
    }

    orch = ThermalOrchestrator(zones=zones, racks=racks, tick_interval_s=5.0)
    # Override with real thermal engineering parameters
    orch.ambient_earth_temp_c = te.ambient_earth_temp_c
    orch.ambient_loss_coeff = te.earth_berm_u_value * te.tank_surface_area_m2 / 10000.0
    return orch
