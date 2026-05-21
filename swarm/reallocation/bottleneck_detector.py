"""
Bottleneck Detector — like a smart home electrical monitor clamped to your breaker panel.

It watches every circuit's current draw, forecasts when the AC will brown out the neighborhood,
and screams before your fridge's compressor trips the main breaker.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Deque, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class PressureLevel(str, Enum):
    """
    Like the color-coded LED on a surge protector.
    """

    GREEN = "green"    # All circuits calm — you could run a hair dryer and a microwave.
    YELLOW = "yellow"  # Getting warm — maybe don't plug in the space heater too.
    ORANGE = "orange"  # Hot to the touch — the breaker is sweating.
    RED = "red"        # Tripped or about to trip — sparks are imminent.


class ResourceType(str, Enum):
    """
    The three main utility lines entering your house.
    """

    GPU = "gpu"       # The heavy 240-volt line for your electric car charger.
    CPU = "cpu"       # The standard 120-volt wall outlets.
    NETWORK = "network"  # The fiber-optic internet cable.


@dataclass
class RingBuffer:
    """
    A circular notepad that only remembers the last N readings.
    Like a Kill-A-Watt meter that auto-scrolls so you never run out of paper.
    """

    maxlen: int = 60
    _buf: Deque[Tuple[float, float]] = field(init=False)
    """Each entry is (timestamp, reading). Like writing '3:15 PM — 12.4 amps' over and over."""

    def __post_init__(self) -> None:
        self._buf = deque(maxlen=self.maxlen)

    def append(self, value: float) -> None:
        """
        Jot down the current amperage with the exact time you read it.
        If the notepad is full, the oldest note falls on the floor.
        """
        self._buf.append((time.monotonic(), value))

    def latest(self) -> Optional[float]:
        """
        What was the most recent number you wrote down?
        Returns None if the notepad is still fresh from the store.
        """
        if not self._buf:
            return None
        return self._buf[-1][1]

    def mean(self, window_sec: Optional[float] = None) -> Optional[float]:
        """
        Average the last few readings.

        Like looking at the last 5 minutes of your smart meter app
        to see if the AC really is running more than usual.
        """
        if not self._buf:
            return None
        cutoff = time.monotonic() - window_sec if window_sec else 0.0
        values = [v for t, v in self._buf if t >= cutoff]
        if not values:
            return None
        return sum(values) / len(values)

    def trend_slope(self, window_sec: float = 30.0) -> Optional[float]:
        """
        Fit a straight line through recent points to see if usage is climbing.

        Like noticing your electric bill gets steeper every summer —
        this calculates exactly how much steeper, in amps per minute.
        """
        if len(self._buf) < 2:
            return None
        cutoff = time.monotonic() - window_sec
        points = [(t, v) for t, v in self._buf if t >= cutoff]
        if len(points) < 2:
            return None
        n = len(points)
        sum_x = sum(t for t, _ in points)
        sum_y = sum(v for _, v in points)
        sum_xy = sum(t * v for t, v in points)
        sum_xx = sum(t * t for t, _ in points)
        denom = n * sum_xx - sum_x * sum_x
        if abs(denom) < 1e-12:
            return 0.0
        slope = (n * sum_xy - sum_x * sum_y) / denom
        return slope


class NodeMetrics(BaseModel):
    """
    A single snapshot from one smart circuit monitor.
    """

    node_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    gpu_util_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    """How hard the GPU is working, 0-100. Like a motor running at half throttle."""

    vram_used_bytes: int = Field(default=0, ge=0)
    """GPU memory currently occupied, in bytes. Like how many extension cords are plugged in."""

    vram_total_bytes: int = Field(default=1, ge=1)
    """Total GPU memory available, in bytes. Like the max amps the sub-panel can handle."""

    cpu_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    """CPU load 0-100. Like every regular outlet in the house groaning under load."""

    network_in_mbps: float = Field(default=0.0, ge=0.0)
    """Data coming down the pipe, in Mbps. Like water pressure into the house."""

    network_out_mbps: float = Field(default=0.0, ge=0.0)
    """Data going out, in Mbps. Like water draining from the house."""

    @property
    def vram_pressure(self) -> float:
        """
        What fraction of the GPU's memory closet is already stuffed with boxes?
        0.0 = empty, 1.0 = you can't close the door.
        """
        return self.vram_used_bytes / self.vram_total_bytes

    @property
    def network_pressure(self) -> float:
        """
        A rough guess at how saturated the internet pipe is.
        We cap at 1000 Mbps assumption if you don't tell us the real pipe size.
        """
        assumed_max = 1000.0
        total = self.network_in_mbps + self.network_out_mbps
        return min(total / assumed_max, 1.0)


class BottleneckForecast(BaseModel):
    """
    The fortune-teller's card for a single node.
    """

    node_id: str
    resource: ResourceType
    current_level: PressureLevel
    forecast_level: PressureLevel
    seconds_until_red: Optional[float]
    """How many seconds before this circuit trips, according to the trend line."""

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    """How sure we are about this prediction. More data = tighter confidence."""

    recommendation: str = Field(default="")
    """Plain English advice, like 'Unplug the space heater now.'"""


class BottleneckDetector:
    """
    The master electrical panel with a digital readout on every circuit.

    It watches amps, watts, and data flowing through every breaker,
    and it can tell you five minutes ahead of time which one is about to pop.
    """

    def __init__(
        self,
        vram_red_threshold: float = 0.95,
        vram_orange_threshold: float = 0.85,
        vram_yellow_threshold: float = 0.70,
        cpu_red_threshold: float = 95.0,
        cpu_orange_threshold: float = 85.0,
        cpu_yellow_threshold: float = 70.0,
        network_red_threshold: float = 0.90,
        network_orange_threshold: float = 0.75,
        network_yellow_threshold: float = 0.50,
        history_length: int = 120,
    ) -> None:
        """
        Install the smart monitor panel and decide what 'too hot' means for your house.

        Like setting the thermostat so the fan kicks on at 72, warns at 78,
        and screams at 85.
        """
        self._vram_red = vram_red_threshold
        self._vram_orange = vram_orange_threshold
        self._vram_yellow = vram_yellow_threshold
        self._cpu_red = cpu_red_threshold
        self._cpu_orange = cpu_orange_threshold
        self._cpu_yellow = cpu_yellow_threshold
        self._net_red = network_red_threshold
        self._net_orange = network_orange_threshold
        self._net_yellow = network_yellow_threshold

        self._history_length = history_length
        self._buffers: Dict[str, Dict[ResourceType, RingBuffer]] = {}
        self._lock = asyncio.Lock()
        self._sample_callbacks: List[Callable[[NodeMetrics], None]] = []

    def on_sample(self, callback: Callable[[NodeMetrics], None]) -> None:
        """
        Hook up a doorbell so every time the meter ticks, someone else hears it too.
        """
        self._sample_callbacks.append(callback)

    def _ensure_buffers(self, node_id: str) -> Dict[ResourceType, RingBuffer]:
        """
        If we haven't installed meters on this room yet, screw them into the wall now.
        """
        if node_id not in self._buffers:
            self._buffers[node_id] = {
                ResourceType.GPU: RingBuffer(maxlen=self._history_length),
                ResourceType.CPU: RingBuffer(maxlen=self._history_length),
                ResourceType.NETWORK: RingBuffer(maxlen=self._history_length),
            }
        return self._buffers[node_id]

    async def record(self, metrics: NodeMetrics) -> None:
        """
        The smart meter just pinged us with a fresh reading.
        Write it down and ring every doorbell that's listening.
        """
        async with self._lock:
            buffers = self._ensure_buffers(metrics.node_id)
            buffers[ResourceType.GPU].append(metrics.vram_pressure)
            buffers[ResourceType.CPU].append(metrics.cpu_percent / 100.0)
            buffers[ResourceType.NETWORK].append(metrics.network_pressure)

        for cb in self._sample_callbacks:
            try:
                cb(metrics)
            except Exception:
                pass

    def _level_for(self, value: float, yellow: float, orange: float, red: float) -> PressureLevel:
        """
        Compare a dial reading against your warning stickers and return the color.
        """
        if value >= red:
            return PressureLevel.RED
        if value >= orange:
            return PressureLevel.ORANGE
        if value >= yellow:
            return PressureLevel.YELLOW
        return PressureLevel.GREEN

    def _current_level(self, metrics: NodeMetrics, resource: ResourceType) -> PressureLevel:
        """
        Look at the latest dial reading for one circuit and tell us its color.
        """
        if resource == ResourceType.GPU:
            return self._level_for(metrics.vram_pressure, self._vram_yellow, self._vram_orange, self._vram_red)
        if resource == ResourceType.CPU:
            return self._level_for(metrics.cpu_percent / 100.0, self._cpu_yellow / 100.0, self._cpu_orange / 100.0, self._cpu_red / 100.0)
        return self._level_for(metrics.network_pressure, self._net_yellow, self._net_orange, self._net_red)

    def _forecast_resource(
        self,
        node_id: str,
        resource: ResourceType,
        current_level: PressureLevel,
        buffers: Dict[ResourceType, RingBuffer],
    ) -> BottleneckForecast:
        """
        Gaze into the crystal ball for one circuit.

        We fit a trend line through recent dial readings.
        If the line is climbing and will cross the RED threshold,
        we calculate how many seconds until the breaker trips.
        """
        buf = buffers[resource]
        slope = buf.trend_slope(window_sec=30.0)
        latest = buf.latest()

        if slope is None or latest is None:
            return BottleneckForecast(
                node_id=node_id,
                resource=resource,
                current_level=current_level,
                forecast_level=current_level,
                seconds_until_red=None,
                confidence=0.0,
                recommendation="Not enough history yet — like trying to predict rain from one cloud.",
            )

        thresholds = {
            ResourceType.GPU: self._vram_red,
            ResourceType.CPU: self._cpu_red / 100.0,
            ResourceType.NETWORK: self._net_red,
        }
        red_line = thresholds[resource]

        if slope <= 0:
            forecast_level = current_level
            seconds_until_red = None
            recommendation = "Usage is flat or falling — like a ceiling fan slowing down."
            confidence = min(1.0, len(buf._buf) / 30.0)
        else:
            gap = red_line - latest
            if gap <= 0:
                forecast_level = PressureLevel.RED
                seconds_until_red = 0.0
                recommendation = "Already at or past the danger line — the breaker is screaming."
                confidence = 1.0
            else:
                seconds_until_red = gap / slope
                if seconds_until_red < 30.0:
                    forecast_level = PressureLevel.RED
                    recommendation = f"Breaker will trip in ~{int(seconds_until_red)} seconds — unplug something NOW."
                elif seconds_until_red < 120.0:
                    forecast_level = PressureLevel.ORANGE
                    recommendation = f"Getting hot — tripping in ~{int(seconds_until_red)} seconds. Start load-shedding."
                elif seconds_until_red < 300.0:
                    forecast_level = PressureLevel.YELLOW
                    recommendation = f"Warm trend — could trip in ~{int(seconds_until_red)} seconds. Keep an eye on it."
                else:
                    forecast_level = PressureLevel.GREEN
                    recommendation = "Trend is up but you have time — like a slow boil."
                confidence = min(1.0, len(buf._buf) / 60.0)

        return BottleneckForecast(
            node_id=node_id,
            resource=resource,
            current_level=current_level,
            forecast_level=forecast_level,
            seconds_until_red=seconds_until_red,
            confidence=confidence,
            recommendation=recommendation,
        )

    async def analyze(self, node_id: str) -> List[BottleneckForecast]:
        """
        Inspect every meter on one room's sub-panel and return three fortune cards.
        """
        async with self._lock:
            if node_id not in self._buffers:
                return []
            buffers = self._buffers[node_id]

        # We need the latest metrics to get current_level, but we can approximate from buffer.
        # For simplicity we use the latest raw value stored.
        results: List[BottleneckForecast] = []
        for resource in (ResourceType.GPU, ResourceType.CPU, ResourceType.NETWORK):
            latest = buffers[resource].latest() or 0.0
            current_level = self._level_for(
                latest,
                {
                    ResourceType.GPU: self._vram_yellow,
                    ResourceType.CPU: self._cpu_yellow / 100.0,
                    ResourceType.NETWORK: self._net_yellow,
                }[resource],
                {
                    ResourceType.GPU: self._vram_orange,
                    ResourceType.CPU: self._cpu_orange / 100.0,
                    ResourceType.NETWORK: self._net_orange,
                }[resource],
                {
                    ResourceType.GPU: self._vram_red,
                    ResourceType.CPU: self._cpu_red / 100.0,
                    ResourceType.NETWORK: self._net_red,
                }[resource],
            )
            forecast = self._forecast_resource(node_id, resource, current_level, buffers)
            results.append(forecast)
        return results

    async def analyze_all(self) -> Dict[str, List[BottleneckForecast]]:
        """
        Walk the whole house, every room, every meter, and collect all fortune cards.
        """
        async with self._lock:
            node_ids = list(self._buffers.keys())
        return {nid: await self.analyze(nid) for nid in node_ids}

    async def is_stalled(
        self,
        node_id: str,
        resource: ResourceType,
        stall_threshold_sec: float = 10.0,
    ) -> Tuple[bool, Optional[str]]:
        """
        Has this circuit been stuck at the exact same reading for too long?

        Like a kitchen timer that stopped ticking — the oven might be broken,
        or someone just paused the microwave.
        """
        async with self._lock:
            if node_id not in self._buffers:
                return False, "No meters installed in this room yet."
            buf = self._buffers[node_id][resource]
            if len(buf._buf) < 2:
                return False, "Not enough history to tell if it's frozen."

            # Check if the oldest reading in the window is identical to the newest.
            oldest_time, oldest_val = buf._buf[0]
            newest_time, newest_val = buf._buf[-1]
            if newest_time - oldest_time < stall_threshold_sec:
                return False, "History window is too short to declare a stall."
            if math.isclose(oldest_val, newest_val, rel_tol=1e-6):
                return True, f"Reading frozen at {newest_val:.4f} for >{stall_threshold_sec}s."
            return False, "Values are changing — the circuit is alive."

    async def hot_nodes(self, min_level: PressureLevel = PressureLevel.ORANGE) -> List[str]:
        """
        Return every room where at least one dial is orange or worse.

        Like walking through the house with a thermal camera and listing
        every outlet that's too hot to touch.
        """
        level_order = [PressureLevel.GREEN, PressureLevel.YELLOW, PressureLevel.ORANGE, PressureLevel.RED]
        min_index = level_order.index(min_level)
        hot: List[str] = []
        async with self._lock:
            for node_id, buffers in self._buffers.items():
                for resource in (ResourceType.GPU, ResourceType.CPU, ResourceType.NETWORK):
                    latest = buffers[resource].latest() or 0.0
                    level = self._level_for(
                        latest,
                        {
                            ResourceType.GPU: self._vram_yellow,
                            ResourceType.CPU: self._cpu_yellow / 100.0,
                            ResourceType.NETWORK: self._net_yellow,
                        }[resource],
                        {
                            ResourceType.GPU: self._vram_orange,
                            ResourceType.CPU: self._cpu_orange / 100.0,
                            ResourceType.NETWORK: self._net_orange,
                        }[resource],
                        {
                            ResourceType.GPU: self._vram_red,
                            ResourceType.CPU: self._cpu_red / 100.0,
                            ResourceType.NETWORK: self._net_red,
                        }[resource],
                    )
                    if level_order.index(level) >= min_index:
                        hot.append(node_id)
                        break
        return hot
