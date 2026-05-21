"""
Telemetry Dashboard Data — Feed structures for web/VS Code dashboards.

ELI5: Imagine a control-room wall covered in big digital gauges, trend charts,
and blinking status lights. This module is the electrician that wires all those
gauges to the same data source. It shapes raw telemetry into neat little JSON
packets that a web page or VS Code panel can slurp up and paint on screen.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Coroutine

from pydantic import BaseModel, Field

from telemetry_analyzer import (
    AnomalyReport,
    PatternMatch,
    TelemetryAnalyzer,
    TimeSlice,
    TrendVector,
)
from telemetry_logger import TelemetryEvent
from adaptive_optimizer import AdaptiveOptimizer, OptimizationAction


# ---------------------------------------------------------------------------
# Dashboard feed models — the faceplates for every gauge
# ---------------------------------------------------------------------------

class MetricCard(BaseModel):
    """
    ELI5: A big round gauge on the wall. It has a needle, a number, and
    a color: green, yellow, or red. This is the blueprint for that gauge.
    """
    card_id: str
    title: str
    value: float
    unit: str = ""
    status: str = "neutral"  # 'good', 'warning', 'critical', 'neutral'
    delta: float | None = None
    timestamp: float = Field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    metadata: dict[str, Any] = Field(default_factory=dict)


class SparklineSeries(BaseModel):
    """
    ELI5: A strip-chart recorder. It draws a wiggly line across a roll of
    paper, showing how a measurement changed over the last few minutes.
    """
    series_id: str
    label: str
    timestamps: list[float]
    values: list[float]
    unit: str = ""
    min_y: float | None = None
    max_y: float | None = None


class HeatmapCell(BaseModel):
    """
    ELI5: One tiny square on a thermal-imaging screen. The hotter the spot,
    the redder the square. Cold spots are blue.
    """
    x_label: str
    y_label: str
    intensity: float = Field(..., ge=0.0, le=1.0)
    tooltip: str = ""


class HeatmapGrid(BaseModel):
    """
    ELI5: The whole thermal-imaging screen made of many tiny colored squares.
    """
    grid_id: str
    title: str
    x_labels: list[str]
    y_labels: list[str]
    cells: list[HeatmapCell]
    updated_at: float = Field(default_factory=lambda: datetime.now(timezone.utc).timestamp())


class AlertBadge(BaseModel):
    """
    ELI5: A flashing red light on the dashboard with a short message.
    'MACHINE 3 OVERHEATING' — that's an alert badge.
    """
    badge_id: str
    severity: str  # 'info', 'warning', 'critical'
    message: str
    source: str
    timestamp: float
    acknowledged: bool = False


class DashboardFrame(BaseModel):
    """
    ELI5: One complete snapshot of the entire control-room wall. Every gauge,
    every chart, every blinking light — all captured in a single photograph.
    """
    frame_id: str
    timestamp: float
    metric_cards: list[MetricCard]
    sparklines: list[SparklineSeries]
    heatmaps: list[HeatmapGrid]
    alerts: list[AlertBadge]
    optimizer_actions: list[OptimizationAction]
    health_summary: dict[str, Any]


# ---------------------------------------------------------------------------
# Feed engine — the electrician wiring gauges to data
# ---------------------------------------------------------------------------

@dataclass
class _FeedBuffer:
    """
    ELI5: A little clipboard behind each gauge. The electrician jots the
    last few numbers on it so the gauge always has something to display,
    even if the main wire flickers.
    """
    sparkline_windows: dict[str, deque[tuple[float, float]]] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=300))
    )
    alert_queue: deque[AlertBadge] = field(default_factory=lambda: deque(maxlen=200))
    last_health: dict[str, Any] = field(default_factory=dict)


def defaultdict(factory):
    from collections import defaultdict as _dd
    return _dd(factory)


class TelemetryDashboardData:
    """
    ELI5: This is the master electrician. They walk around the control room,
    read every sensor, and update every gauge, strip chart, and blinking light.
    They also offer a live video feed (Server-Sent Events style) so remote
    operators can watch the wall from anywhere.
    """

    def __init__(
        self,
        analyzer: TelemetryAnalyzer,
        optimizer: AdaptiveOptimizer,
        frame_interval_sec: float = 1.0,
    ) -> None:
        # ELI5: The electrician memorizes which analyzer and optimizer to talk to,
        # and how often to walk the room (default: once per second).
        self._analyzer = analyzer
        self._optimizer = optimizer
        self._frame_interval_sec = frame_interval_sec
        self._buffer = _FeedBuffer()
        self._subscribers: list[Callable[[DashboardFrame], Coroutine[Any, Any, None]]] = []
        self._running: bool = False
        self._task: asyncio.Task[Any] | None = None

    # ------------------------------------------------------------------
    # Lifecycle — start and stop the electrician's rounds
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """
        ELI5: Flip the main breaker for the control room. The electrician
        begins their regular walking rounds.
        """
        self._running = True
        self._task = asyncio.create_task(self._frame_loop())

    async def stop(self) -> None:
        """
        ELI5: Flip the breaker off. The electrician finishes the current round,
        then sits down. All gauges freeze at their last reading.
        """
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    # ------------------------------------------------------------------
    # Subscription — remote operators watching the wall
    # ------------------------------------------------------------------

    def subscribe(self, callback: Callable[[DashboardFrame], Coroutine[Any, Any, None]]) -> None:
        """
        ELI5: A remote operator plugs a monitor into the wall. Every time the
        electrician finishes a round, the monitor gets a fresh photograph.
        """
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[DashboardFrame], Coroutine[Any, Any, None]]) -> None:
        """
        ELI5: The operator unplugs their monitor. They stop receiving updates.
        """
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    async def event_stream(self) -> AsyncIterator[str]:
        """
        ELI5: This is a live TV broadcast feed. It yields one JSON photograph
        after another, forever, until the operator changes the channel.
        Perfect for Server-Sent Events (SSE) in a browser or VS Code webview.
        """
        queue: asyncio.Queue[DashboardFrame] = asyncio.Queue()

        async def _enqueue(frame: DashboardFrame) -> None:
            await queue.put(frame)

        self.subscribe(_enqueue)
        try:
            while self._running:
                frame = await asyncio.wait_for(queue.get(), timeout=5.0)
                yield f"data: {frame.model_dump_json()}\n\n"
        except asyncio.TimeoutError:
            pass
        finally:
            self.unsubscribe(_enqueue)

    # ------------------------------------------------------------------
    # Frame builder — the electrician's clipboard for one full round
    # ------------------------------------------------------------------

    async def build_frame(self, frame_id: str | None = None) -> DashboardFrame:
        """
        ELI5: The electrician walks every aisle, reads every sensor, and snaps
        one complete photograph of the entire control-room wall.
        """
        now = datetime.now(timezone.utc).timestamp()
        fid = frame_id or f"frame_{int(now * 1000)}"

        health = await self._analyzer.current_health()
        self._buffer.last_health = health

        cards = await self._build_metric_cards(health, now)
        sparklines = await self._build_sparklines(now)
        heatmaps = await self._build_heatmaps(now)
        alerts = await self._build_alerts(now)
        actions = await self._optimizer.recent_actions(limit=10)

        return DashboardFrame(
            frame_id=fid,
            timestamp=now,
            metric_cards=cards,
            sparklines=sparklines,
            heatmaps=heatmaps,
            alerts=alerts,
            optimizer_actions=actions,
            health_summary=health,
        )

    async def _build_metric_cards(
        self,
        health: dict[str, Any],
        now: float,
    ) -> list[MetricCard]:
        """
        ELI5: The electrician stops at the four big round gauges and writes
        down the current numbers: throughput, latency, error rate, and queue depth.
        """
        throughput_1m = sum((health.get("throughput_1m") or {}).values())
        throughput_5m = sum((health.get("throughput_5m") or {}).values())

        delta = throughput_1m - (throughput_5m / 5.0) if throughput_5m else 0.0
        status = "good"
        if health.get("status") == "degraded":
            status = "warning"
        elif health.get("status") == "stalled":
            status = "critical"

        cards = [
            MetricCard(
                card_id="throughput_1m",
                title="Throughput (1 min)",
                value=float(throughput_1m),
                unit="evt/min",
                status=status,
                delta=round(delta, 2),
                timestamp=now,
            ),
            MetricCard(
                card_id="buffer_depth",
                title="Buffered Events",
                value=float(health.get("buffered_events", 0)),
                unit="events",
                status="neutral",
                timestamp=now,
            ),
        ]

        # Add optimizer budget card if available
        opt_state = await self._optimizer.get_state()
        budget = opt_state.budget
        qps_ratio = budget.current_qps / max(budget.max_qps, 1.0)
        budget_status = "good"
        if qps_ratio > 0.9:
            budget_status = "critical"
        elif qps_ratio > 0.7:
            budget_status = "warning"

        cards.append(
            MetricCard(
                card_id="qps_ratio",
                title="QPS Utilization",
                value=round(qps_ratio * 100, 2),
                unit="%",
                status=budget_status,
                timestamp=now,
                metadata={
                    "current_qps": budget.current_qps,
                    "max_qps": budget.max_qps,
                    "latency_p99": budget.current_latency_p99,
                },
            )
        )

        return cards

    async def _build_sparklines(self, now: float) -> list[SparklineSeries]:
        """
        ELI5: The electrician unrolls the strip-chart paper and copies the
        last few hundred dots into a neat little packet for the monitor.
        """
        series_list: list[SparklineSeries] = []

        # Throughput sparkline from health snapshots
        # ELI5: We fake a rolling 'current_qps' by sampling throughput_1m
        tput = self._buffer.last_health.get("throughput_1m", {})
        total = sum(tput.values())
        self._buffer.sparkline_windows["throughput_1m"].append((now, total))

        ts_vals = list(self._buffer.sparkline_windows["throughput_1m"])
        if ts_vals:
            series_list.append(
                SparklineSeries(
                    series_id="throughput_1m",
                    label="Throughput (events / min)",
                    timestamps=[t for t, _ in ts_vals],
                    values=[v for _, v in ts_vals],
                    unit="evt/min",
                    min_y=min(v for _, v in ts_vals) if len(ts_vals) > 1 else None,
                    max_y=max(v for _, v in ts_vals) if len(ts_vals) > 1 else None,
                )
            )

        return series_list

    async def _build_heatmaps(self, now: float) -> list[HeatmapGrid]:
        """
        ELI5: The electrician points the thermal camera at the factory floor.
        Hot zones (lots of events) glow red; cold zones (idle machines) glow blue.
        """
        health = self._buffer.last_health
        throughput = health.get("throughput_1m", {})
        if not throughput:
            return []

        max_val = max(throughput.values()) if throughput else 1
        cells: list[HeatmapCell] = []
        for src, count in throughput.items():
            intensity = min(count / max(max_val, 1), 1.0)
            cells.append(
                HeatmapCell(
                    x_label=src,
                    y_label="1m",
                    intensity=round(intensity, 4),
                    tooltip=f"{src}: {count} events/min",
                )
            )

        return [
            HeatmapGrid(
                grid_id="source_heatmap",
                title="Event Heatmap by Source (1 min)",
                x_labels=list(throughput.keys()),
                y_labels=["1m"],
                cells=cells,
                updated_at=now,
            )
        ]

    async def _build_alerts(self, now: float) -> list[AlertBadge]:
        """
        ELI5: The electrician scans every blinking light. New red lights get
        copied onto the alert clipboard. Old ones that have been acknowledged
        are left alone.
        """
        # Pull recent optimizer actions that look like alerts
        actions = await self._optimizer.recent_actions(limit=5)
        alerts: list[AlertBadge] = []

        for action in actions:
            if action.confidence > 0.7:
                severity = "critical" if action.confidence > 0.9 else "warning"
                badge = AlertBadge(
                    badge_id=f"opt_{action.action_id}",
                    severity=severity,
                    message=f"[{action.category}] {action.reason}",
                    source="adaptive_optimizer",
                    timestamp=action.timestamp,
                    acknowledged=False,
                )
                self._buffer.alert_queue.append(badge)

        # De-duplicate by badge_id
        seen: set[str] = set()
        unique: list[AlertBadge] = []
        for badge in reversed(self._buffer.alert_queue):
            if badge.badge_id not in seen:
                seen.add(badge.badge_id)
                unique.append(badge)
        unique.reverse()
        return unique[-20:]

    # ------------------------------------------------------------------
    # Background loop — the electrician's walking rounds
    # ------------------------------------------------------------------

    async def _frame_loop(self) -> None:
        """
        ELI5: Every second, the electrician walks the room, snaps a photo,
        and slides copies under every remote operator's door.
        """
        while self._running:
            try:
                frame = await self.build_frame()
                for sub in self._subscribers:
                    try:
                        await sub(frame)
                    except Exception:
                        pass  # ELI5: One monitor is unplugged; don't stop for it.
                await asyncio.sleep(self._frame_interval_sec)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(self._frame_interval_sec)

    # ------------------------------------------------------------------
    # Manual snapshot — ask the electrician for a single photo
    # ------------------------------------------------------------------

    async def snapshot(self) -> dict[str, Any]:
        """
        ELI5: The supervisor walks in and says, 'Give me the numbers right now.'
        The electrician snaps one photo and hands it over as a plain dictionary.
        """
        frame = await self.build_frame()
        return frame.model_dump(mode="json")

    async def snapshot_json(self) -> str:
        """
        ELI5: Same photo, but printed on a postcard (JSON string) so it can
        be mailed to a web browser.
        """
        frame = await self.build_frame()
        return frame.model_dump_json()
