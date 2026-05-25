"""
simple_swarm_orchestrator.py
============================
Connects MassAgentOrchestrator to the TestRunner.
Spawns parallel agents for each phase, collects results,
and generates a final report.

ELI5: A foreman who hires workers for each inspection job,
      watches them work, and writes the final report.
"""
from __future__ import annotations

import time
import threading
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

from .computer_controller import ComputerController
from .test_runner import TestRunner, PhaseResult, CheckResult


# ---------------------------------------------------------------------------
# Agent task definitions (callable payloads for MassAgentOrchestrator)
# ---------------------------------------------------------------------------

def _phase_worker(phase_name: str, controller: ComputerController, skip_destructive: bool = True) -> dict:
    """Worker function that runs a single test phase."""
    runner = TestRunner(controller, skip_destructive=skip_destructive)

    phase_map = {
        "thermal": runner.phase_1_thermal_stress,
        "sensor": runner.phase_2_sensor_network,
        "analysis": runner.phase_3_build_analysis,
        "links": runner.phase_4_link_verification,
        "ui": runner.phase_5_ui_integration,
        "shutdown": runner.phase_6_graceful_shutdown,
        "coldstart": runner.phase_7_cold_start,
    }

    fn = phase_map.get(phase_name)
    if not fn:
        return {"error": f"Unknown phase: {phase_name}"}

    try:
        result = fn()
        return {
            "phase": result.phase,
            "status": result.status,
            "checks": [
                {"name": c.name, "status": c.status, "notes": c.notes}
                for c in result.checks
            ],
            "duration_sec": result.duration_sec,
            "screenshots": result.screenshots,
        }
    except Exception as e:
        return {"phase": phase_name, "status": "FAIL", "checks": [
            {"name": "exception", "status": "FAIL", "notes": str(e)}
        ], "duration_sec": 0}


def _api_test_worker(controller: ComputerController) -> dict:
    """Agent that runs phases 1-4 (pure HTTP, no UI)."""
    runner = TestRunner(controller)
    results = []
    for fn in [runner.phase_1_thermal_stress, runner.phase_2_sensor_network,
               runner.phase_3_build_analysis, runner.phase_4_link_verification]:
        try:
            results.append(fn())
        except Exception as e:
            results.append(PhaseResult(phase=fn.__name__, status="FAIL",
                         checks=[CheckResult("exception", "FAIL", str(e))]))
    return {"results": [_phase_result_to_dict(r) for r in results]}


def _ui_test_worker(controller: ComputerController) -> dict:
    """Agent that runs phase 5 (UI automation)."""
    runner = TestRunner(controller)
    result = runner.phase_5_ui_integration()
    return _phase_result_to_dict(result)


def _shutdown_worker(controller: ComputerController) -> dict:
    """Agent that runs phase 6 (graceful shutdown)."""
    runner = TestRunner(controller)
    result = runner.phase_6_graceful_shutdown()
    return _phase_result_to_dict(result)


def _coldstart_worker(controller: ComputerController) -> dict:
    """Agent that runs phase 7 (cold start)."""
    runner = TestRunner(controller)
    result = runner.phase_7_cold_start()
    return _phase_result_to_dict(result)


def _watchdog_worker(controller: ComputerController, interval: int = 5, max_shots: int = 20) -> dict:
    """Agent that captures screenshots continuously."""
    shots = []
    for i in range(max_shots):
        res = controller.screenshot(save=True, filename=f"watchdog_{int(time.time())}.png")
        if res.get("success") and res.get("path"):
            shots.append(res["path"])
        time.sleep(interval)
    return {"screenshots": shots, "count": len(shots)}


def _phase_result_to_dict(result: PhaseResult) -> dict:
    return {
        "phase": result.phase,
        "status": result.status,
        "checks": [
            {"name": c.name, "status": c.status, "notes": c.notes}
            for c in result.checks
        ],
        "duration_sec": result.duration_sec,
        "screenshots": result.screenshots,
    }


# ---------------------------------------------------------------------------
# SimpleSwarmOrchestrator
# ---------------------------------------------------------------------------

@dataclass
class SwarmTestState:
    running: bool = False
    started_at: float = 0.0
    finished_at: Optional[float] = None
    phases_completed: int = 0
    phases_total: int = 7
    results: List[dict] = field(default_factory=list)
    screenshots: List[str] = field(default_factory=list)
    log: List[str] = field(default_factory=list)
    final_report: str = ""


class SimpleSwarmOrchestrator:
    """
    Orchestrates the full 7-phase test using parallel MassAgent workers.
    """

    def __init__(self, max_agents: int = 8, skip_destructive: bool = True):
        self.max_agents = max_agents
        self.skip_destructive = skip_destructive
        self.state = SwarmTestState()
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._controller: Optional[ComputerController] = None

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def start_test(self, parallel: bool = True) -> dict:
        """Start the full test suite. Returns immediately; check status() for progress."""
        with self._lock:
            if self.state.running:
                return {"success": False, "error": "Test already running"}
            self.state = SwarmTestState(running=True, started_at=time.time())

        self._thread = threading.Thread(target=self._run_test, args=(parallel, self.skip_destructive), daemon=True)
        self._thread.start()
        return {"success": True, "message": "Test started", "parallel": parallel, "skip_destructive": self.skip_destructive}

    def stop_test(self) -> dict:
        """Stop a running test."""
        with self._lock:
            self.state.running = False
        return {"success": True, "message": "Test stop requested"}

    def status(self) -> dict:
        """Get current test status."""
        with self._lock:
            elapsed = round(time.time() - self.state.started_at, 1) if self.state.started_at else 0
            return {
                "running": self.state.running,
                "phases_completed": self.state.phases_completed,
                "phases_total": self.state.phases_total,
                "elapsed_sec": elapsed,
                "latest_results": self.state.results[-3:] if self.state.results else [],
            }

    def get_results(self) -> dict:
        """Get all completed results."""
        with self._lock:
            return {
                "running": self.state.running,
                "phases_completed": self.state.phases_completed,
                "results": self.state.results,
                "screenshots": self.state.screenshots,
                "final_report": self.state.final_report,
            }

    # -----------------------------------------------------------------------
    # Internal runner
    # -----------------------------------------------------------------------

    def _log(self, msg: str):
        with self._lock:
            self.state.log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def _run_test(self, parallel: bool, skip_destructive: bool = True):
        """Main test execution thread."""
        self._controller = ComputerController()
        self._log(f"Test runner initialized (skip_destructive={skip_destructive})")

        try:
            if parallel:
                self._run_parallel()
            else:
                self._run_sequential()
        except Exception as e:
            self._log(f"Test runner error: {e}")
        finally:
            with self._lock:
                self.state.running = False
                self.state.finished_at = time.time()
                self.state.final_report = self._generate_report()
            self._log("Test complete")

    def _run_sequential(self, skip_destructive: bool = True):
        """Run all phases in order (safer, no screen contention)."""
        runner = TestRunner(self._controller, skip_destructive=skip_destructive)
        for result in runner.run_all_phases():
            with self._lock:
                self.state.results.append(_phase_result_to_dict(result))
                self.state.phases_completed += 1
                self.state.screenshots.extend(result.screenshots)
            self._log(f"Phase complete: {result.phase} -> {result.status}")

    def _run_parallel(self, skip_destructive: bool = True):
        """
        Run phases in parallel where safe:
        - API agents (1-4) run in parallel
        - UI agent (5) runs alone (owns screen)
        - Shutdown (6) and cold start (7) run sequentially after (if not skipped)
        - Watchdog runs continuously
        """
        import concurrent.futures

        results: Dict[str, dict] = {}

        # Phase A: Parallel API tests (phases 1-4)
        self._log("Spawning API test agents (phases 1-4)")
        api_tasks = {
            "thermal": lambda: _phase_worker("thermal", self._controller, skip_destructive),
            "sensor": lambda: _phase_worker("sensor", self._controller, skip_destructive),
            "analysis": lambda: _phase_worker("analysis", self._controller, skip_destructive),
            "links": lambda: _phase_worker("links", self._controller, skip_destructive),
        }

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futures = {ex.submit(fn): name for name, fn in api_tasks.items()}
            for future in concurrent.futures.as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result(timeout=60)
                except Exception as e:
                    results[name] = {"phase": name, "status": "FAIL", "error": str(e)}
                with self._lock:
                    self.state.results.append(results[name])
                    self.state.phases_completed += 1
                self._log(f"API agent done: {name}")

        # Phase B: UI automation (phase 5) -- must be alone on screen
        self._log("Running UI automation agent (phase 5)")
        ui_result = _phase_worker("ui", self._controller, skip_destructive)
        with self._lock:
            self.state.results.append(ui_result)
            self.state.phases_completed += 1
            self.state.screenshots.extend(ui_result.get("screenshots", []))
        self._log("UI agent done")

        # Phase C: Shutdown (phase 6) -- skipped if running inside backend
        if not skip_destructive:
            self._log("Running shutdown agent (phase 6)")
            shutdown_result = _phase_worker("shutdown", self._controller, skip_destructive)
            with self._lock:
                self.state.results.append(shutdown_result)
                self.state.phases_completed += 1
            self._log("Shutdown agent done")
        else:
            self._log("Skipping Phase 6 (shutdown) -- destructive")

        # Phase D: Cold start (phase 7) -- skipped if running inside backend
        if not skip_destructive:
            self._log("Running cold start agent (phase 7)")
            coldstart_result = _phase_worker("coldstart", self._controller, skip_destructive)
            with self._lock:
                self.state.results.append(coldstart_result)
                self.state.phases_completed += 1
            self._log("Cold start agent done")
        else:
            self._log("Skipping Phase 7 (cold start) -- destructive")

    def _generate_report(self) -> str:
        """Generate a markdown report from collected results."""
        lines = ["# SimpleSwarm -- Autonomous Test Report", ""]
        lines.append(f"**Started:** {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.state.started_at))}")
        if self.state.finished_at:
            dur = round(self.state.finished_at - self.state.started_at, 1)
            lines.append(f"**Duration:** {dur}s")
        lines.append(f"**Phases:** {self.state.phases_completed} / {self.state.phases_total}")
        lines.append("")

        for r in self.state.results:
            icon = "PASS" if r.get("status") == "PASS" else "FAIL"
            lines.append(f"## {r.get('phase', '?')} -- {icon}")
            for c in r.get("checks", []):
                cicon = "PASS" if c.get("status") == "PASS" else "FAIL"
                lines.append(f"- [{cicon}] {c.get('name', '?')}")
                if c.get("notes"):
                    lines.append(f"  - {c['notes']}")
            lines.append("")

        return "\n".join(lines)
