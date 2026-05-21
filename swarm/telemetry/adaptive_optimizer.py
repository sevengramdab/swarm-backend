"""
Adaptive Optimizer — Self-improving routing, prompt, and resource optimization.

ELI5: Imagine a smart CNC machine that watches its own tool wear. When it
notices the cutter getting dull, it automatically slows the feed rate, swaps
to a sharper tool, or asks for a coolant boost. Over weeks, it learns which
speeds give the best surface finish for each material. This module is that
brain: it reads telemetry, tweaks the knobs, and remembers what worked.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

import aiofiles
from pydantic import BaseModel, Field, field_validator

from telemetry_analyzer import TelemetryAnalyzer, TrendVector
from telemetry_logger import TelemetryEvent


# ---------------------------------------------------------------------------
# Optimizer models — the CNC's parameter cards
# ---------------------------------------------------------------------------

class RouteConfig(BaseModel):
    """
    ELI5: This is the tool-path card. It says which cutting tool (agent)
    to use, how fast to spin it, and which direction to move first.
    """
    target_id: str = Field(..., description="Which agent or endpoint gets the job.")
    weight: float = Field(default=1.0, ge=0.0, description="Preference score, like feed-rate override.")
    timeout_sec: float = Field(default=30.0, ge=0.1)
    retry_limit: int = Field(default=3, ge=0)
    tags: dict[str, str] = Field(default_factory=dict)


class PromptTemplate(BaseModel):
    """
    ELI5: This is the engineering drawing template. It has placeholder
    callouts like <<DIM_A>> that get filled in with real numbers at runtime.
    The optimizer tweaks which template produces the cleanest parts.
    """
    template_id: str
    template_text: str
    version: int = 1
    avg_score: float = 0.0
    usage_count: int = 0


class ResourceBudget(BaseModel):
    """
    ELI5: This is the shop-floor energy meter. It tracks how much electricity,
    coolant, and compressed air we are allowed to use this shift.
    """
    max_concurrent: int = Field(default=10, ge=1)
    max_qps: float = Field(default=100.0, ge=1.0)
    max_latency_p99: float = Field(default=5.0, ge=0.01)
    current_qps: float = 0.0
    current_latency_p99: float = 0.0


class OptimizationAction(BaseModel):
    """
    ELI5: The CNC brain prints a tiny sticky note that says:
    'Turn knob X from 4.2 to 3.8 because parts started chattering.'
    """
    action_id: str
    timestamp: float
    category: str  # 'route', 'prompt', 'resource'
    parameter: str
    old_value: Any
    new_value: Any
    reason: str
    confidence: float = Field(..., ge=0.0, le=1.0)

    @field_validator("action_id")
    @classmethod
    def _not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("action_id must not be blank.")
        return v


class OptimizerState(BaseModel):
    """
    ELI5: The CNC's memory chip. It stores every knob position ever tried,
    the quality grade for each, and the current 'best known' settings.
    """
    routes: dict[str, RouteConfig] = Field(default_factory=dict)
    prompts: dict[str, PromptTemplate] = Field(default_factory=dict)
    budget: ResourceBudget = Field(default_factory=ResourceBudget)
    action_history: deque[OptimizationAction] = Field(default_factory=lambda: deque(maxlen=1000))
    score_history: dict[str, deque[float]] = Field(default_factory=lambda: defaultdict(lambda: deque(maxlen=500)))


# ---------------------------------------------------------------------------
# Score trackers — like DRO readouts on a mill
# ---------------------------------------------------------------------------

@dataclass
class _ScoreTracker:
    """
    ELI5: A digital readout that shows the average dimension of the last
    hundred parts. It smooths out jitter so the operator sees a steady number.
    """
    window: deque[float] = field(default_factory=lambda: deque(maxlen=200))
    ema: float = 0.0
    ema_alpha: float = 0.1

    def push(self, value: float) -> None:
        """ELI5: Feed in a fresh measurement; the DRO updates."""
        self.window.append(value)
        if self.ema == 0.0 and len(self.window) == 1:
            self.ema = value
        else:
            self.ema = self.ema_alpha * value + (1 - self.ema_alpha) * self.ema

    def mean(self) -> float:
        """ELI5: Plain arithmetic average of the window."""
        return sum(self.window) / len(self.window) if self.window else 0.0

    def std(self) -> float:
        """ELI5: How spread out the measurements are — big spread means unstable."""
        if len(self.window) < 2:
            return 0.0
        m = self.mean()
        variance = sum((x - m) ** 2 for x in self.window) / len(self.window)
        return math.sqrt(variance)


# ---------------------------------------------------------------------------
# Adaptive Optimizer
# ---------------------------------------------------------------------------

class AdaptiveOptimizer:
    """
    ELI5: This is the CNC's adaptive controller. It does three jobs:
    1. **Routing** — picks the sharpest tool for the next cut.
    2. **Prompt tuning** — chooses the drawing template that yields the
       tightest tolerances.
    3. **Resource guarding** — throttles feed rate when the spindle is
       overheating, and opens the floodgates when it cools down.
    Every decision is scored. Bad scores make the brain try something else.
    Good scores make it double down.
    """

    def __init__(
        self,
        analyzer: TelemetryAnalyzer,
        state_path: Path | None = None,
        save_interval_sec: float = 30.0,
    ) -> None:
        # ELI5: Load the memory chip, or start fresh if this is a new machine.
        self._analyzer = analyzer
        self._state_path = state_path or Path("./optimizer_state.json")
        self._save_interval_sec = save_interval_sec
        self._state = OptimizerState()
        self._scores: dict[str, _ScoreTracker] = defaultdict(_ScoreTracker)
        self._lock: asyncio.Lock = asyncio.Lock()
        self._saver_task: asyncio.Task[Any] | None = None
        self._shutdown: bool = False

    # ------------------------------------------------------------------
    # Lifecycle — power on / power off
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """
        ELI5: Flip the main breaker. Load saved settings from the memory chip.
        Start the auto-save timer so nothing is lost if the lights flicker.
        """
        await self._load_state()
        self._saver_task = asyncio.create_task(self._auto_save_loop())

    async def stop(self) -> None:
        """
        ELI5: Hit the E-stop. Save one last time, then shut down safely.
        """
        self._shutdown = True
        if self._saver_task is not None:
            self._saver_task.cancel()
            try:
                await self._saver_task
            except asyncio.CancelledError:
                pass
        await self._persist_state()

    async def __aenter__(self) -> "AdaptiveOptimizer":
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.stop()

    # ------------------------------------------------------------------
    # Routing — picking the sharpest tool
    # ------------------------------------------------------------------

    async def register_route(self, config: RouteConfig) -> None:
        """
        ELI5: Add a new cutting tool to the tool magazine. Give it a part
        number and a default speed setting.
        """
        async with self._lock:
            self._state.routes[config.target_id] = config

    async def select_route(
        self,
        job_tags: dict[str, str] | None = None,
        strategy: str = "weighted_best",
    ) -> RouteConfig | None:
        """
        ELI5: The operator asks, 'Which tool should I use for this job?'
        The brain looks at every tool's recent quality scores and picks one.
        - weighted_best = favor the sharpest tool, but still try others sometimes.
        - round_robin = use every tool in turn to keep them all calibrated.
        - explore = deliberately pick an untested tool to gather data.
        """
        async with self._lock:
            candidates = list(self._state.routes.values())
            if not candidates:
                return None

            if strategy == "round_robin":
                idx = int(time.time()) % len(candidates)
                return candidates[idx]

            if strategy == "explore":
                min_usage = min(c.usage_count for c in candidates)
                unexplored = [c for c in candidates if c.usage_count == min_usage]
                return random.choice(unexplored)

            # weighted_best: compute composite score = weight * (1 + normalized EMA)
            scored: list[tuple[float, RouteConfig]] = []
            for c in candidates:
                tracker = self._scores.get(c.target_id)
                ema = tracker.ema if tracker else 0.5
                composite = c.weight * (1.0 + ema)
                scored.append((composite, c))
            scored.sort(key=lambda x: x[0], reverse=True)
            return scored[0][1] if scored else None

    async def score_route(self, target_id: str, score: float) -> None:
        """
        ELI5: After a cut finishes, the quality inspector grades it A-F.
        The brain records that grade next to the tool's part number.
        """
        async with self._lock:
            self._scores[target_id].push(score)
            if target_id in self._state.routes:
                self._state.routes[target_id].weight = max(
                    0.01, self._state.routes[target_id].weight + (score - 0.5) * 0.1
                )

    # ------------------------------------------------------------------
    # Prompt tuning — choosing the best drawing template
    # ------------------------------------------------------------------

    async def register_prompt(self, template: PromptTemplate) -> None:
        """
        ELI5: Slide a new drawing template into the file cabinet. Each template
        has a version number so we can track which revision works best.
        """
        async with self._lock:
            self._state.prompts[template.template_id] = template

    async def select_prompt(self, strategy: str = "best") -> PromptTemplate | None:
        """
        ELI5: The drafter asks, 'Which template gives the cleanest dimensions?'
        The brain picks the one with the highest average score.
        """
        async with self._lock:
            candidates = list(self._state.prompts.values())
            if not candidates:
                return None
            if strategy == "best":
                candidates.sort(key=lambda t: t.avg_score, reverse=True)
                chosen = candidates[0]
                chosen.usage_count += 1
                return chosen
            if strategy == "explore":
                min_usage = min(t.usage_count for t in candidates)
                pool = [t for t in candidates if t.usage_count == min_usage]
                chosen = random.choice(pool)
                chosen.usage_count += 1
                return chosen
            return random.choice(candidates)

    async def score_prompt(self, template_id: str, score: float) -> None:
        """
        ELI5: The QC inspector grades the drawing produced from a template.
        The brain updates the template's running average so future picks are smarter.
        """
        async with self._lock:
            if template_id not in self._state.prompts:
                return
            pt = self._state.prompts[template_id]
            pt.avg_score = (pt.avg_score * pt.usage_count + score) / (pt.usage_count + 1)
            pt.usage_count += 1
            self._scores[f"prompt:{template_id}"].push(score)

    # ------------------------------------------------------------------
    # Resource guarding — the coolant and spindle watchdog
    # ------------------------------------------------------------------

    async def update_budget(self, budget: ResourceBudget) -> None:
        """
        ELI5: The shop supervisor posts a new energy allowance on the bulletin
        board. The brain reads it and will throttle feed rates if needed.
        """
        async with self._lock:
            self._state.budget = budget

    async def check_resource_gate(self, estimated_cost: float = 1.0) -> dict[str, Any]:
        """
        ELI5: Before starting a new cut, the brain asks:
        'Is the spindle too hot? Are we over the power budget?'
        It returns a green/yellow/red light plus a recommended feed override.
        """
        async with self._lock:
            budget = self._state.budget

        throttle = 1.0
        status = "green"

        if budget.current_qps > budget.max_qps:
            status = "red"
            throttle = budget.max_qps / max(budget.current_qps, 1.0)
        elif budget.current_qps > budget.max_qps * 0.8:
            status = "yellow"
            throttle = 0.8

        if budget.current_latency_p99 > budget.max_latency_p99:
            status = "red"
            throttle = min(throttle, 0.5)

        allowed = status != "red" or estimated_cost < throttle
        return {
            "status": status,
            "throttle": round(throttle, 4),
            "allowed": allowed,
            "current_qps": budget.current_qps,
            "current_latency_p99": budget.current_latency_p99,
        }

    async def apply_resource_throttle(self, telemetry_event: TelemetryEvent) -> OptimizationAction | None:
        """
        ELI5: The temperature alarm just blared. The brain quickly decides
        whether to lower feed rate, pause new jobs, or increase coolant flow.
        It reads the recent trend line to guess whether things will get worse.
        """
        trend = await self._analyzer.trend(
            metric_extractor=lambda ev: float(ev.tags.get("latency_ms", 0)),
            window_count=50,
        )
        async with self._lock:
            budget = self._state.budget

        action: OptimizationAction | None = None
        if trend.direction == "rising" and budget.current_latency_p99 > budget.max_latency_p99 * 0.8:
            new_qps = max(1.0, budget.max_qps * 0.7)
            action = OptimizationAction(
                action_id=f"throttle_{int(time.time() * 1000)}",
                timestamp=datetime.now(timezone.utc).timestamp(),
                category="resource",
                parameter="max_qps",
                old_value=budget.max_qps,
                new_value=round(new_qps, 2),
                reason=f"Latency rising (trend slope {trend.slope:.4f}); pre-emptive throttle.",
                confidence=round(min(abs(trend.slope) * 10, 1.0), 4),
            )
            budget.max_qps = new_qps
        elif trend.direction == "falling" and budget.current_latency_p99 < budget.max_latency_p99 * 0.4:
            new_qps = min(budget.max_qps * 1.15, budget.max_qps * 2.0)
            action = OptimizationAction(
                action_id=f"unthrottle_{int(time.time() * 1000)}",
                timestamp=datetime.now(timezone.utc).timestamp(),
                category="resource",
                parameter="max_qps",
                old_value=budget.max_qps,
                new_value=round(new_qps, 2),
                reason=f"Latency falling (trend slope {trend.slope:.4f}); easing throttle.",
                confidence=round(min(abs(trend.slope) * 10, 1.0), 4),
            )
            budget.max_qps = new_qps

        if action:
            async with self._lock:
                self._state.action_history.append(action)
        return action

    # ------------------------------------------------------------------
    # Self-tuning loop — the CNC running its own calibration cycle
    # ------------------------------------------------------------------

    async def run_tuning_cycle(self) -> list[OptimizationAction]:
        """
        ELI5: Once per shift, the CNC runs a self-test. It checks every tool's
        wear, every template's accuracy, and every resource limit. It prints
        a list of sticky-note adjustments.
        """
        actions: list[OptimizationAction] = []
        async with self._lock:
            # Tune routes: demote stale tools, promote sharp ones
            for tid, tracker in list(self._scores.items()):
                if tid.startswith("prompt:"):
                    continue
                if tid not in self._state.routes:
                    continue
                std = tracker.std()
                if std > 0.3:
                    # Too much chatter — dampen weight
                    old = self._state.routes[tid].weight
                    new = max(0.1, old * 0.9)
                    actions.append(
                        OptimizationAction(
                            action_id=f"tune_route_{tid}_{int(time.time() * 1000)}",
                            timestamp=datetime.now(timezone.utc).timestamp(),
                            category="route",
                            parameter=f"route:{tid}:weight",
                            old_value=old,
                            new_value=round(new, 4),
                            reason=f"High score variance (std={std:.4f}); damping weight.",
                            confidence=round(min(std, 1.0), 4),
                        )
                    )
                    self._state.routes[tid].weight = new

            # Tune prompts: retire low-scoring templates
            for pid, pt in list(self._state.prompts.items()):
                if pt.usage_count > 20 and pt.avg_score < 0.3:
                    actions.append(
                        OptimizationAction(
                            action_id=f"retire_prompt_{pid}_{int(time.time() * 1000)}",
                            timestamp=datetime.now(timezone.utc).timestamp(),
                            category="prompt",
                            parameter=f"prompt:{pid}:avg_score",
                            old_value=pt.avg_score,
                            new_value=None,
                            reason=f"Prompt consistently underperforming ({pt.avg_score:.3f}); consider revision.",
                            confidence=round(1.0 - pt.avg_score, 4),
                        )
                    )

        return actions

    # ------------------------------------------------------------------
    # Persistence — saving the memory chip
    # ------------------------------------------------------------------

    async def _auto_save_loop(self) -> None:
        """
        ELI5: A little battery-backed clock ticks every 30 seconds. Each tick,
        the brain writes its current settings to the memory chip so a power
        outage doesn't erase the week's learning.
        """
        while not self._shutdown:
            try:
                await asyncio.sleep(self._save_interval_sec)
            except asyncio.CancelledError:
                break
            await self._persist_state()

    async def _persist_state(self) -> None:
        """
        ELI5: Open the memory chip drawer, write every knob position in neat
        JSON handwriting, and slide the drawer shut.
        """
        async with self._lock:
            snapshot = self._state.model_dump(
                mode="json",
                exclude_none=True,
            )
        snapshot["action_history"] = list(snapshot.get("action_history", []))
        snapshot["score_history"] = {
            k: list(v) for k, v in snapshot.get("score_history", {}).items()
        }
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self._state_path, "w") as f:
            await f.write(json.dumps(snapshot, indent=2))

    async def _load_state(self) -> None:
        """
        ELI5: Power-on self-test. If a memory chip is already in the drawer,
        read it. If the drawer is empty, start with factory defaults.
        """
        if not self._state_path.exists():
            return
        async with aiofiles.open(self._state_path, "r") as f:
            raw = await f.read()
        data = json.loads(raw)
        # Hydrate routes
        for k, v in data.get("routes", {}).items():
            self._state.routes[k] = RouteConfig(**v)
        # Hydrate prompts
        for k, v in data.get("prompts", {}).items():
            self._state.prompts[k] = PromptTemplate(**v)
        # Hydrate budget
        if "budget" in data:
            self._state.budget = ResourceBudget(**data["budget"])
        # Restore action history as a bounded deque
        self._state.action_history = deque(
            [OptimizationAction(**a) for a in data.get("action_history", [])],
            maxlen=1000,
        )

    # ------------------------------------------------------------------
    # Introspection — reading the parameter cards
    # ------------------------------------------------------------------

    async def get_state(self) -> OptimizerState:
        """
        ELI5: The supervisor asks to see the current settings board. We hand
        them a photocopy so they can't accidentally bump a knob.
        """
        async with self._lock:
            # Return a shallow copy snapshot via Pydantic re-parse
            return OptimizerState.model_validate_json(self._state.model_dump_json())

    async def recent_actions(self, limit: int = 50) -> list[OptimizationAction]:
        """
        ELI5: Show the last N sticky notes the brain printed, newest first.
        """
        async with self._lock:
            return list(self._state.action_history)[-limit:]
