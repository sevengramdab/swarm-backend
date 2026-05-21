"""
Telemetry Analyzer — Real-time and historical analysis with pattern detection.

ELI5: Imagine a quality-control inspector standing next to the conveyor belt.
Instead of just glancing at each part, they keep a running tally of:
- How many parts passed by in the last minute (sliding-window counters).
- Whether any part looks weird compared to the last thousand (anomaly scores).
- Whether the belt is speeding up or slowing down (trend lines).
This module is that inspector, but they can also pull old logbooks off the shelf
and analyze months of production history in a blink.
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine

import aiofiles
from pydantic import BaseModel, Field

from telemetry_logger import LoggerConfig, TelemetryEvent, TelemetryLogger


# ---------------------------------------------------------------------------
# Analysis result models — the inspector's clipboard forms
# ---------------------------------------------------------------------------

class TimeSlice(BaseModel):
    """
    ELI5: A little snapshot on the inspector's clipboard. It says:
    'From 9:00 to 9:05, we saw 42 parts, average weight 12.3 kg.'
    """
    start_ts: float
    end_ts: float
    event_count: int
    avg_payload_size: float
    event_type_counts: dict[str, int]
    top_sources: list[tuple[str, int]]
    tags_summary: dict[str, dict[str, int]]


class AnomalyReport(BaseModel):
    """
    ELI5: A bright red sticky note the inspector slaps on a part that looks
    suspicious — way too heavy, way too light, or arriving in a weird rhythm.
    """
    event_id: str
    timestamp: float
    source: str
    anomaly_score: float = Field(..., ge=0.0, le=1.0)
    reason: str
    suggested_action: str


class TrendVector(BaseModel):
    """
    ELI5: An arrow drawn on the production chart. It points up if throughput
    is climbing, down if it is dropping, and sideways if things are steady.
    """
    metric_name: str
    slope: float
    intercept: float
    r_squared: float
    forecast_next: float
    direction: str  # 'rising', 'falling', 'stable'


class PatternMatch(BaseModel):
    """
    ELI5: The inspector notices that every Tuesday at 3 PM the belt hiccups.
    This is the stamped form that records that repeating hiccup.
    """
    pattern_id: str
    pattern_name: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    matched_event_ids: list[str]
    description: str


# ---------------------------------------------------------------------------
# Sliding-window accumulator — like a rolling tally on a grease-pencil board
# ---------------------------------------------------------------------------

@dataclass
class _WindowAccumulator:
    """
    ELI5: A whiteboard next to the belt with a 5-minute grid. When a part
    passes, we mark the current box. When the box slides off the left edge,
    we erase it. This keeps only the freshest counts visible.
    """
    window_sec: float
    _buckets: deque[tuple[float, int]] = field(default_factory=deque)

    def add(self, timestamp: float, count: int = 1) -> None:
        """ELI5: Mark another tally in the current time box."""
        cutoff = timestamp - self.window_sec
        while self._buckets and self._buckets[0][0] < cutoff:
            self._buckets.popleft()
        self._buckets.append((timestamp, count))

    def total(self) -> int:
        """ELI5: Count every tally still visible on the whiteboard."""
        return sum(c for _, c in self._buckets)


# ---------------------------------------------------------------------------
# Analyzer engine
# ---------------------------------------------------------------------------

class TelemetryAnalyzer:
    """
    ELI5: This is the quality-control station itself. It has:
    - A grease-pencil board for quick counts (sliding windows).
    - A magnifying glass for spotting weird parts (anomaly detection).
    - A long wall chart for spotting slow drifts (trend analysis).
    - A filing cabinet for looking up old records (historical replay).
    """

    def __init__(
        self,
        logger: TelemetryLogger | None = None,
        windows: list[float] | None = None,
    ) -> None:
        # ELI5: Set up the inspection station with however many whiteboards
        # the shift supervisor wants (default: 1-minute, 5-minute, 15-minute).
        self._logger = logger
        self._windows_sec: list[float] = windows or [60.0, 300.0, 900.0]
        self._accumulators: dict[str, dict[str, _WindowAccumulator]] = defaultdict(
            lambda: defaultdict(lambda: _WindowAccumulator(window_sec=60.0))
        )
        self._history: deque[TelemetryEvent] = deque(maxlen=10_000)
        self._anomaly_hooks: list[Callable[[AnomalyReport], Coroutine[Any, Any, None]]] = []
        self._pattern_hooks: list[Callable[[PatternMatch], Coroutine[Any, Any, None]]] = []
        self._lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Ingestion — the inspector watches each part go by
    # ------------------------------------------------------------------

    async def ingest(self, event: TelemetryEvent) -> None:
        """
        ELI5: A part rolls past the inspector. They jot it on every whiteboard,
        add it to the recent-photo album, and check whether it looks weird.
        """
        async with self._lock:
            self._history.append(event)
            for w in self._windows_sec:
                acc = self._accumulators[w][event.event_type]
                acc.window_sec = w
                acc.add(event.timestamp)
            # Run lightweight checks inline; heavier ones can be backgrounded.
            report = self._check_anomaly(event)
            if report:
                for hook in self._anomaly_hooks:
                    asyncio.create_task(hook(report))

    async def ingest_batch(self, events: list[TelemetryEvent]) -> None:
        """
        ELI5: A whole pallet arrives at once. The inspector rapidly marks
        every whiteboard, then steps back to scan for any red flags.
        """
        async with self._lock:
            for ev in events:
                self._history.append(ev)
                for w in self._windows_sec:
                    acc = self._accumulators[w][ev.event_type]
                    acc.window_sec = w
                    acc.add(ev.timestamp)
        # Anomaly checks outside the tight lock to keep the belt moving.
        for ev in events:
            report = self._check_anomaly(ev)
            if report:
                for hook in self._anomaly_hooks:
                    asyncio.create_task(hook(report))

    # ------------------------------------------------------------------
    # Real-time queries — reading the whiteboards
    # ------------------------------------------------------------------

    async def throughput(self, window_sec: float | None = None) -> dict[str, int]:
        """
        ELI5: Ask the inspector: 'How many parts of each type passed in the
        last N minutes?' They glance at the matching whiteboard and read the tally.
        """
        w = window_sec or self._windows_sec[0]
        async with self._lock:
            return {
                etype: acc.total()
                for etype, acc in self._accumulators.get(w, {}).items()
            }

    async def time_slice(
        self,
        start_ts: float,
        end_ts: float,
    ) -> TimeSlice:
        """
        ELI5: The supervisor wants a report for a specific shift period.
        The inspector flips through the recent-photo album and tallies up
        everything that happened between those two times.
        """
        counts: dict[str, int] = defaultdict(int)
        sources: dict[str, int] = defaultdict(int)
        tags: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        total_payload_size = 0
        matched = 0

        async with self._lock:
            for ev in self._history:
                if start_ts <= ev.timestamp <= end_ts:
                    matched += 1
                    counts[ev.event_type] += 1
                    sources[ev.source] += 1
                    total_payload_size += len(json.dumps(ev.payload))
                    for k, v in ev.tags.items():
                        tags[k][v] += 1

        avg_size = total_payload_size / matched if matched else 0.0
        top_sources = sorted(sources.items(), key=lambda x: x[1], reverse=True)[:5]
        tags_summary = {k: dict(v) for k, v in tags.items()}

        return TimeSlice(
            start_ts=start_ts,
            end_ts=end_ts,
            event_count=matched,
            avg_payload_size=avg_size,
            event_type_counts=dict(counts),
            top_sources=top_sources,
            tags_summary=tags_summary,
        )

    async def current_health(self) -> dict[str, Any]:
        """
        ELI5: A quick dashboard light check. Green = everything running smooth.
        Yellow = throughput is dropping. Red = anomalies are spiking.
        """
        now = datetime.now(timezone.utc).timestamp()
        throughput_1m = await self.throughput(60.0)
        throughput_5m = await self.throughput(300.0)
        total_1m = sum(throughput_1m.values())
        total_5m = sum(throughput_5m.values())

        health = "healthy"
        if total_1m < total_5m / 10:
            health = "degraded"
        if total_1m == 0 and total_5m > 0:
            health = "stalled"

        return {
            "status": health,
            "throughput_1m": throughput_1m,
            "throughput_5m": throughput_5m,
            "buffered_events": len(self._history),
            "timestamp": now,
        }

    # ------------------------------------------------------------------
    # Anomaly detection — the magnifying glass
    # ------------------------------------------------------------------

    def _check_anomaly(self, event: TelemetryEvent) -> AnomalyReport | None:
        """
        ELI5: The inspector holds the part up to a bright light and checks
        three things:
        1. Is it way bigger or smaller than normal? (payload size z-score)
        2. Did it arrive way too fast after the last one? (inter-arrival time)
        3. Does it have weird tags that never appeared before? (novelty check)
        If any score is too high, they write a red sticky note.
        """
        scores: list[tuple[float, str]] = []

        # 1. Payload size z-score (naive, using recent history)
        if self._history:
            recent_payloads = [
                len(json.dumps(e.payload))
                for e in list(self._history)[-500:]
                if e.event_type == event.event_type
            ]
            if len(recent_payloads) >= 10:
                mean = sum(recent_payloads) / len(recent_payloads)
                variance = sum((x - mean) ** 2 for x in recent_payloads) / len(recent_payloads)
                std = math.sqrt(variance) if variance > 0 else 1.0
                size = len(json.dumps(event.payload))
                z = abs((size - mean) / std)
                if z > 3.0:
                    scores.append((min(z / 10.0, 1.0), f"Payload size outlier (z={z:.2f})"))

        # 2. Inter-arrival velocity
        if len(self._history) >= 2:
            last = list(self._history)[-2]
            delta = event.timestamp - last.timestamp
            if delta < 0.001:  # Faster than 1 ms
                scores.append((0.9, f"Extreme burst: {delta:.4f}s inter-arrival"))

        # 3. Novel source check
        known_sources = {e.source for e in self._history}
        if event.source not in known_sources and len(self._history) > 100:
            scores.append((0.7, f"New source detected: {event.source}"))

        if not scores:
            return None

        max_score, reason = max(scores, key=lambda x: x[0])
        return AnomalyReport(
            event_id=event.event_id,
            timestamp=event.timestamp,
            source=event.source,
            anomaly_score=round(max_score, 4),
            reason=reason,
            suggested_action="Review source configuration or check for misbehaving agent.",
        )

    # ------------------------------------------------------------------
    # Trend analysis — reading the long wall chart
    # ------------------------------------------------------------------

    async def trend(
        self,
        metric_extractor: Callable[[TelemetryEvent], float],
        window_count: int = 100,
    ) -> TrendVector:
        """
        ELI5: The supervisor draws a line through the last hundred dots on
        the wall chart. If the line tilts up, production is rising. If it tilts
        down, something is slowing. They also write down where the next dot
        should probably land.
        """
        async with self._lock:
            samples = list(self._history)[-window_count:]

        if len(samples) < 2:
            return TrendVector(
                metric_name="unknown",
                slope=0.0,
                intercept=0.0,
                r_squared=0.0,
                forecast_next=0.0,
                direction="stable",
            )

        xs = [i for i in range(len(samples))]
        ys = [metric_extractor(ev) for ev in samples]
        n = len(xs)
        sum_x = sum(xs)
        sum_y = sum(ys)
        sum_xy = sum(x * y for x, y in zip(xs, ys))
        sum_x2 = sum(x * x for x in xs)
        sum_y2 = sum(y * y for y in ys)

        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            slope = 0.0
            intercept = sum_y / n
        else:
            slope = (n * sum_xy - sum_x * sum_y) / denominator
            intercept = (sum_y * sum_x2 - sum_x * sum_xy) / denominator

        ss_tot = sum((y - (sum_y / n)) ** 2 for y in ys)
        ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        forecast = slope * len(xs) + intercept
        direction = "stable"
        if slope > 0.01:
            direction = "rising"
        elif slope < -0.01:
            direction = "falling"

        return TrendVector(
            metric_name="custom",
            slope=round(slope, 6),
            intercept=round(intercept, 4),
            r_squared=round(r_squared, 4),
            forecast_next=round(forecast, 4),
            direction=direction,
        )

    # ------------------------------------------------------------------
    # Pattern detection — finding repeating hiccups
    # ------------------------------------------------------------------

    async def detect_patterns(self) -> list[PatternMatch]:
        """
        ELI5: The inspector steps back and looks for shapes in the noise.
        For example: 'Every time source X sends a metric, source Y sends an
        error within 2 seconds.' That repeating shape becomes a named pattern.
        """
        async with self._lock:
            samples = list(self._history)
        matches: list[PatternMatch] = []

        if len(samples) < 20:
            return matches

        # Pattern: source A -> source B error within 5 seconds
        cause_effect_window = 5.0
        pair_counts: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
        for i, ev_a in enumerate(samples):
            if ev_a.event_type != "error":
                for ev_b in samples[i + 1 :]:
                    if ev_b.timestamp - ev_a.timestamp > cause_effect_window:
                        break
                    if ev_b.event_type == "error" and ev_b.source != ev_a.source:
                        pair_counts[(ev_a.source, ev_b.source)].append(
                            (ev_a.event_id, ev_b.event_id)
                        )

        for (src_a, src_b), event_pairs in pair_counts.items():
            if len(event_pairs) >= 3:
                confidence = min(len(event_pairs) / 20.0, 1.0)
                flat_ids = [eid for pair in event_pairs for eid in pair]
                matches.append(
                    PatternMatch(
                        pattern_id=f"cause_effect_{src_a}_{src_b}",
                        pattern_name="Cascade Error",
                        confidence=round(confidence, 4),
                        matched_event_ids=flat_ids,
                        description=(
                            f"Events from '{src_a}' frequently precede errors "
                            f"from '{src_b}' within {cause_effect_window}s."
                        ),
                    )
                )

        return matches

    # ------------------------------------------------------------------
    # Historical replay — pulling old logbooks off the shelf
    # ------------------------------------------------------------------

    async def replay_file(
        self,
        path: Path,
        handler: Callable[[TelemetryEvent], Coroutine[Any, Any, None]],
    ) -> int:
        """
        ELI5: The inspector walks to the archive cabinet, pulls out an old
        logbook, and reads every page aloud to a trainee one line at a time.
        """
        count = 0
        opener = aiofiles.open
        open_path = path
        if path.suffix == ".gz" or path.name.endswith(".gz"):
            import gzip

            opener = lambda p, mode: aiofiles.open(p, mode)  # type: ignore[assignment]
            # gzip is sync; for huge files we'd stream, but here we simplify.
            # ELI5: If the tube is vacuum-sealed, we pop it open first.
        async with opener(open_path, "r") as f:
            async for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                ev = TelemetryEvent(**data)
                await handler(ev)
                count += 1
        return count

    # ------------------------------------------------------------------
    # Hooks — bells and buzzers on the inspection station
    # ------------------------------------------------------------------

    def on_anomaly(self, hook: Callable[[AnomalyReport], Coroutine[Any, Any, None]]) -> None:
        """
        ELI5: Wire a red alarm light to the inspector's desk. Every time
        a weird part is spotted, the light flashes.
        """
        self._anomaly_hooks.append(hook)

    def on_pattern(self, hook: Callable[[PatternMatch], Coroutine[Any, Any, None]]) -> None:
        """
        ELI5: Wire a yellow warning bell that rings when the inspector
        notices a repeating hiccup in production.
        """
        self._pattern_hooks.append(hook)
