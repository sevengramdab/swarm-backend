#!/usr/bin/env python3
"""
orchestrator_bridge.py
======================
Adapter that wraps the real MassAgentOrchestrator so the FastAPI
web UI can talk to it without knowing internal details.

ELI5: The real foreman (MassAgentOrchestrator) speaks construction
slang.  This translator converts it to plain English for the
building manager's clipboard (FastAPI JSON).
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.mass_agent_swarm import MassAgentOrchestrator, Task
from bridge.llm_worker import llm_worker_fn


class OrchestratorBridge:
    """
    Thin wrapper around MassAgentOrchestrator that exposes the
    exact interface the FastAPI routers expect.
    """

    def __init__(
        self,
        max_agents: int = 10,
        initial_agents: int = 3,
        task_timeout: float = 30.0,
        auto_scale: bool = True,
    ) -> None:
        self._orch = MassAgentOrchestrator(
            max_agents=max_agents,
            initial_agents=initial_agents,
            task_timeout=task_timeout,
            worker_fn=llm_worker_fn,
            auto_scale=auto_scale,
        )
        self._start_time: Optional[float] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Power on the swarm."""
        if not self._orch._running:
            self._orch.start()
            self._start_time = time.time()

    def shutdown(self, wait: bool = True, timeout: Optional[float] = None) -> None:
        """Power off the swarm."""
        self._orch.shutdown(wait=wait, timeout=timeout)
        self._start_time = None

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Return a JSON-safe status snapshot."""
        raw = self._orch.status()
        uptime = 0.0
        if self._start_time:
            uptime = time.time() - self._start_time
        return {
            "running": raw["running"],
            "agents_total": raw["agents_total"],
            "agents_active": raw["agents_active"],
            "agents_idle": raw["agents_idle"],
            "pending_tasks": raw["pending_tasks"],
            "completed_tasks": raw["completed_tasks"],
            "failed_tasks": raw["failed_tasks"],
            "uptime_seconds": round(uptime, 1),
        }

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    @property
    def agents(self) -> Dict[str, Dict[str, Any]]:
        """
        Return agents as plain dicts (not dataclasses with threading.Thread).
        FastAPI needs JSON-serializable objects.
        """
        result: Dict[str, Dict[str, Any]] = {}
        for agent_id, state in self._orch.agents.items():
            result[agent_id] = {
                "agent_id": state.agent_id,
                "status": "running" if state.task else "idle",
                "tasks_completed": state.tasks_completed,
                "tasks_failed": state.tasks_failed,
                "node_id": "local",  # bridge runs locally; could be extended
                "uptime": round(time.time() - state.spawned_at, 1),
                "alive": state.alive,
                "last_heartbeat": state.last_heartbeat,
            }
        return result

    def _kill_agent(self, agent_id: str, reason: str = "api_request") -> None:
        """Trip one agent's breaker manually."""
        self._orch._kill_agent(agent_id, reason=reason)

    def _remove_agent(self, agent_id: str) -> bool:
        """Remove a dead agent from the registry."""
        return self._orch._remove_agent(agent_id)

    def _set_agent_config(self, agent_id: str, config: Dict[str, Any]) -> bool:
        """Update per-agent configuration."""
        return self._orch._set_agent_config(agent_id, config)

    def get_agent_config(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get current config for an agent."""
        agent = self._orch.agents.get(agent_id)
        if agent:
            return dict(agent.config) if agent.config else {}
        return None

    def get_active_tasks(self) -> List[Dict[str, Any]]:
        """List all tasks currently being processed."""
        result = []
        for agent_id, state in self._orch.agents.items():
            if state.task:
                result.append({
                    "task_id": state.task.id,
                    "agent_id": agent_id,
                    "status": state.task.status.name.lower(),
                    "prompt": (state.task.payload or {}).get("prompt", "")[:100],
                    "model": (state.task.payload or {}).get("model", ""),
                    "started_at": state.task.started_at,
                })
        return result

    # ------------------------------------------------------------------
    # Task submission (advanced)
    # ------------------------------------------------------------------

    def submit_task(self, payload: Any) -> str:
        """Queue a new task and return its ID."""
        task = Task(payload=payload)
        return self._orch.submit_task(task)

    def submit_inference(self, prompt: str, **kwargs: Any) -> str:
        """Queue an inference job.  The worker will process it."""
        payload = {"prompt": prompt, "type": "inference", **kwargs}
        return self.submit_task(payload)

    def list_models(self) -> list:
        """List available Ollama models."""
        try:
            import urllib.request
            import json
            req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return ["llama3.2"]

    def get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a completed or failed task by ID."""
        task = self._orch.get_task(task_id)
        if task is None:
            return None
        return {
            "task_id": task.id,
            "status": task.status.name.lower(),
            "result": task.result,
            "error": task.error,
            "assigned_agent": task.assigned_agent,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "finished_at": task.finished_at,
            "retry_count": task.retry_count,
        }
