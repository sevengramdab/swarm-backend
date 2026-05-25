#!/usr/bin/env python3
"""
Mass Agent Swarm Orchestrator
=============================
Dynamically spawns, monitors, and manages agent workers.
If an agent hangs, it is killed and replaced; tasks are redistributed.

Usage:
    from mass_agent_swarm import MassAgentOrchestrator, Task
    
    orch = MassAgentOrchestrator(max_agents=10, task_timeout=30)
    orch.submit_task(Task(id="1", payload={"cmd": "echo hello"}))
    orch.start()
    orch.wait_for_completion()
    orch.shutdown()
"""

from __future__ import annotations

import os
import sys
import time
import json
import uuid
import signal
import logging
import threading
import traceback
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue, Empty
from datetime import datetime

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("MassAgent")

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class TaskStatus(Enum):
    PENDING = auto()
    ASSIGNED = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    TIMEOUT = auto()


@dataclass
class Task:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    payload: Any = None
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: Optional[str] = None
    result: Any = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    retry_count: int = 0
    max_retries: int = 3
    rescue_count: int = 0
    max_rescues: int = 3


@dataclass
class AgentState:
    agent_id: str
    thread: threading.Thread
    task: Optional[Task] = None
    last_heartbeat: float = field(default_factory=time.time)
    spawned_at: float = field(default_factory=time.time)
    tasks_completed: int = 0
    tasks_failed: int = 0
    alive: bool = True
    shutdown: bool = False
    config: Dict[str, Any] = field(default_factory=dict)  # per-agent model, temp, etc.


# ---------------------------------------------------------------------------
# Default worker implementation (can be swapped)
# ---------------------------------------------------------------------------

def default_worker_fn(task: Task) -> Any:
    """
    Default worker function. Expects task.payload to be either:
      - A callable  -> calls it with no args
      - A dict with 'cmd' -> runs shell command via os.system
      - A dict with 'py'  -> exec() the Python code string
      - Anything else -> returned as-is
    """
    payload = task.payload

    if callable(payload):
        return payload()

    if isinstance(payload, dict):
        if "cmd" in payload:
            code = os.system(payload["cmd"])
            return {"exit_code": code}
        if "py" in payload:
            local_ns: Dict[str, Any] = {"task": task, "result": None}
            exec(payload["py"], local_ns)
            return local_ns.get("result")
        if "sleep" in payload:
            time.sleep(payload["sleep"])
            return {"slept": payload["sleep"]}

    return payload


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class MassAgentOrchestrator:
    """
    Mass Agent Swarm Orchestrator.

    Parameters
    ----------
    max_agents : int
        Hard ceiling on concurrent agents.
    initial_agents : int
        Agents to spawn immediately on start().
    task_timeout : float
        Seconds before a running task is considered hung.
    heartbeat_interval : float
        Seconds between watchdog checks.
    worker_fn : Callable[[Task], Any]
        Function each agent invokes to process a task.
    auto_scale : bool
        Whether to spawn extra agents when load is high or hangs occur.
    scale_up_threshold : float
        If queued_tasks / active_agents > threshold, scale up.
    """

    def __init__(
        self,
        max_agents: int = 20,
        initial_agents: int = 4,
        task_timeout: float = 30.0,
        heartbeat_interval: float = 5.0,
        worker_fn: Callable[[Task], Any] = default_worker_fn,
        auto_scale: bool = True,
        scale_up_threshold: float = 2.0,
    ):
        self.max_agents = max_agents
        self.initial_agents = initial_agents
        self.task_timeout = task_timeout
        self.heartbeat_interval = heartbeat_interval
        self.worker_fn = worker_fn
        self.auto_scale = auto_scale
        self.scale_up_threshold = scale_up_threshold

        # Task queues
        self.pending_queue: Queue[Task] = Queue()
        self.completed_tasks: Dict[str, Task] = {}
        self.failed_tasks: Dict[str, Task] = {}
        self._completed_task_ids: Set[str] = set()

        # Agent registry
        self.agents: Dict[str, AgentState] = {}
        self._agent_counter = 0
        self._lock = threading.RLock()

        # Control flags
        self._running = False
        self._watchdog_thread: Optional[threading.Thread] = None
        self._scheduler_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()

        # Stats
        self.stats = {
            "tasks_submitted": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "tasks_timed_out": 0,
            "agents_spawned": 0,
            "agents_killed": 0,
            "start_time": None,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit_task(self, task: Task) -> str:
        """Queue a task and return its ID."""
        with self._lock:
            self.stats["tasks_submitted"] += 1
        self.pending_queue.put(task)
        logger.info(f"Task {task.id} submitted.")
        return task.id

    def submit_many(self, tasks: List[Task]) -> List[str]:
        """Queue multiple tasks."""
        return [self.submit_task(t) for t in tasks]

    def start(self) -> None:
        """Start the orchestrator: spawn initial agents, start watchdog & scheduler."""
        if self._running:
            logger.warning("Orchestrator already running.")
            return

        self._running = True
        self._shutdown_event.clear()
        self.stats["start_time"] = time.time()

        logger.info("=== MASS AGENT SWARM ACTIVATED ===")
        logger.info(f"Spawning {self.initial_agents} initial agents...")

        for _ in range(self.initial_agents):
            self._spawn_agent()

        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()

        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._scheduler_thread.start()

    def shutdown(self, wait: bool = True, timeout: Optional[float] = None) -> None:
        """Graceful shutdown. Optionally wait for queued tasks to finish."""
        logger.info("Shutdown signal received...")
        self._running = False
        self._shutdown_event.set()

        if wait:
            deadline = time.time() + (timeout or self.task_timeout * 2)
            while time.time() < deadline:
                with self._lock:
                    active = sum(1 for a in self.agents.values() if a.task is not None)
                    pending = self.pending_queue.qsize()
                if active == 0 and pending == 0:
                    break
                time.sleep(0.5)

        # Signal all agents to die
        with self._lock:
            for agent in self.agents.values():
                agent.shutdown = True

        # Wait a moment for threads to exit
        time.sleep(1.0)
        logger.info("=== MASS AGENT SWARM DEACTIVATED ===")
        self._print_stats()

    def wait_for_completion(self, poll_interval: float = 1.0) -> None:
        """Block until all pending and active tasks are finished."""
        while True:
            with self._lock:
                active = sum(1 for a in self.agents.values() if a.task is not None)
                pending = self.pending_queue.qsize()
            if active == 0 and pending == 0:
                break
            time.sleep(poll_interval)

    def get_task(self, task_id: str) -> Optional[Task]:
        """Retrieve a task by ID — checks active, pending, completed, and failed."""
        with self._lock:
            # Check active tasks first (agents currently working)
            for agent in self.agents.values():
                if agent.task and agent.task.id == task_id:
                    return agent.task
            # Check pending queue
            for task in list(self.pending_queue.queue):
                if task.id == task_id:
                    return task
            if task_id in self.completed_tasks:
                return self.completed_tasks[task_id]
            if task_id in self.failed_tasks:
                return self.failed_tasks[task_id]
        return None

    def status(self) -> Dict[str, Any]:
        """Snapshot of current orchestrator status."""
        with self._lock:
            return {
                "running": self._running,
                "agents_total": len(self.agents),
                "agents_active": sum(1 for a in self.agents.values() if a.task is not None),
                "agents_idle": sum(1 for a in self.agents.values() if a.task is None and a.alive),
                "pending_tasks": self.pending_queue.qsize(),
                "completed_tasks": len(self.completed_tasks),
                "failed_tasks": len(self.failed_tasks),
                "stats": self.stats.copy(),
            }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _spawn_agent(self) -> Optional[str]:
        """Spawn a new agent worker thread. Returns agent_id or None at limit."""
        with self._lock:
            if len(self.agents) >= self.max_agents:
                logger.warning("Max agents reached; cannot spawn more.")
                return None

            self._agent_counter += 1
            agent_id = f"AGENT-{self._agent_counter:03d}"
            state = AgentState(
                agent_id=agent_id,
                thread=threading.Thread(target=self._agent_loop, args=(agent_id,), daemon=True),
            )
            self.agents[agent_id] = state
            self.stats["agents_spawned"] += 1
            state.thread.start()
            logger.info(f"Spawned {agent_id} (total: {len(self.agents)})")
            return agent_id

    def _kill_agent(self, agent_id: str, reason: str = "unknown") -> None:
        """Mark an agent for death. The agent loop will exit on next check."""
        with self._lock:
            agent = self.agents.get(agent_id)
            if not agent:
                return
            logger.warning(f"Killing {agent_id}: {reason}")
            agent.alive = False
            agent.shutdown = True
            self.stats["agents_killed"] += 1

            # Requeue its current task if there is one
            if agent.task and agent.task.status in (TaskStatus.RUNNING, TaskStatus.ASSIGNED):
                task = agent.task
                task.status = TaskStatus.PENDING
                task.assigned_agent = None
                task.error = f"Agent killed: {reason}"
                task.retry_count += 1
                task.started_at = None
                if task.retry_count <= task.max_retries:
                    logger.info(f"Requeuing task {task.id} (retry {task.retry_count})")
                    self.pending_queue.put(task)
                else:
                    logger.error(f"Task {task.id} exhausted retries.")
                    task.status = TaskStatus.FAILED
                    self.failed_tasks[task.id] = task
                    self.stats["tasks_failed"] += 1
                agent.task = None

    def _remove_agent(self, agent_id: str) -> bool:
        """Force-remove a dead agent from the registry. Returns True if removed."""
        with self._lock:
            agent = self.agents.get(agent_id)
            if not agent:
                return False
            if agent.alive:
                logger.warning(f"Cannot remove alive agent {agent_id}; kill it first")
                return False
            self.agents.pop(agent_id, None)
            logger.info(f"Removed dead agent {agent_id} from registry")
            return True

    def _set_agent_config(self, agent_id: str, config: Dict[str, Any]) -> bool:
        """Update per-agent configuration (model, temperature, etc.)."""
        with self._lock:
            agent = self.agents.get(agent_id)
            if not agent:
                return False
            agent.config.update(config)
            logger.info(f"Updated config for {agent_id}: {config}")
            return True

    def _agent_loop(self, agent_id: str) -> None:
        """Main loop for each agent worker."""
        while not self._shutdown_event.is_set():
            with self._lock:
                agent = self.agents.get(agent_id)
                if not agent or agent.shutdown or not agent.alive:
                    break

            try:
                # Block briefly for a task
                task = self.pending_queue.get(timeout=1.0)
            except Empty:
                continue

            # Claim the task
            with self._lock:
                agent = self.agents.get(agent_id)
                if not agent or not agent.alive:
                    # Put it back if we're dying
                    self.pending_queue.put(task)
                    break
                agent.task = task
                agent.last_heartbeat = time.time()

            task.status = TaskStatus.RUNNING
            task.assigned_agent = agent_id
            task.started_at = time.time()
            logger.info(f"{agent_id} started task {task.id}")

            try:
                result = self.worker_fn(task)

                # Guard against double-completion when multiple agents race the same task.
                with self._lock:
                    already_done = task.id in self._completed_task_ids
                    if not already_done:
                        self._completed_task_ids.add(task.id)

                if already_done:
                    logger.info(f"{agent_id} finished task {task.id} but another agent already completed it — discarding")
                    with self._lock:
                        agent = self.agents.get(agent_id)
                        if agent:
                            agent.tasks_completed += 1
                            agent.last_heartbeat = time.time()
                            agent.task = None
                    continue

                task.result = result
                task.status = TaskStatus.COMPLETED
                task.finished_at = time.time()
                with self._lock:
                    agent = self.agents.get(agent_id)
                    if agent:
                        agent.tasks_completed += 1
                        agent.last_heartbeat = time.time()
                        agent.task = None
                    self.completed_tasks[task.id] = task
                    self.stats["tasks_completed"] += 1
                logger.info(f"{agent_id} completed task {task.id}")

            except Exception as exc:
                task.error = traceback.format_exc()
                task.status = TaskStatus.FAILED
                task.finished_at = time.time()
                task.retry_count += 1
                with self._lock:
                    agent = self.agents.get(agent_id)
                    if agent:
                        agent.tasks_failed += 1
                        agent.last_heartbeat = time.time()
                        agent.task = None

                if task.retry_count <= task.max_retries:
                    logger.warning(
                        f"{agent_id} failed task {task.id}, retrying "
                        f"({task.retry_count}/{task.max_retries})"
                    )
                    task.status = TaskStatus.PENDING
                    task.assigned_agent = None
                    task.started_at = None
                    self.pending_queue.put(task)
                else:
                    logger.error(f"Task {task.id} exhausted retries.")
                    with self._lock:
                        self.failed_tasks[task.id] = task
                        self.stats["tasks_failed"] += 1

        # Cleanup
        with self._lock:
            self.agents.pop(agent_id, None)
        logger.info(f"{agent_id} exited.")

    def _watchdog_loop(self) -> None:
        """Periodically checks agents for hangs (no heartbeat progress)."""
        logger.info("Watchdog started.")
        while not self._shutdown_event.is_set():
            time.sleep(self.heartbeat_interval)
            now = time.time()

            with self._lock:
                agents_snapshot = list(self.agents.values())

            for agent in agents_snapshot:
                if not agent.alive:
                    continue
                # If agent has been running a task too long without finishing,
                # DON'T kill it — spawn a helper and requeue the task.
                if agent.task and agent.task.started_at:
                    elapsed = now - agent.task.started_at
                    if elapsed > self.task_timeout:
                        task = agent.task
                        if task.rescue_count >= task.max_rescues:
                            logger.warning(
                                f"{agent.agent_id} still hung on {task.id} "
                                f"(rescue limit {task.max_rescues} reached) — leaving it alone"
                            )
                            continue

                        task.rescue_count += 1
                        task.status = TaskStatus.PENDING
                        task.assigned_agent = None
                        task.started_at = None
                        self.pending_queue.put(task)
                        agent.task = None  # detach so agent is free for next task
                        self.stats["tasks_timed_out"] += 1
                        logger.warning(
                            f"{agent.agent_id} hung on {task.id} for {elapsed:.1f}s — "
                            f"rescued (attempt {task.rescue_count}/{task.max_rescues})"
                        )

                        if self.auto_scale:
                            self._spawn_agent()

            # Auto-scale: if queue depth per agent is high, spawn more
            if self.auto_scale:
                with self._lock:
                    pending = self.pending_queue.qsize()
                    active = sum(1 for a in self.agents.values() if a.task is not None)
                    total = len(self.agents)
                    idle = total - active

                if pending > 0 and idle == 0 and total < self.max_agents:
                    # All agents busy and tasks waiting
                    ratio = pending / max(active, 1)
                    if ratio > self.scale_up_threshold:
                        to_spawn = min(int(ratio), self.max_agents - total)
                        logger.info(
                            f"Auto-scaling: spawning {to_spawn} extra agents "
                            f"(queue={pending}, active={active})"
                        )
                        for _ in range(to_spawn):
                            self._spawn_agent()

        logger.info("Watchdog stopped.")

    def _scheduler_loop(self) -> None:
        """Optional advanced scheduler (currently a placeholder for priority tweaks)."""
        logger.info("Scheduler started.")
        while not self._shutdown_event.is_set():
            time.sleep(self.heartbeat_interval * 2)
            # Could implement priority reordering, task batching, etc.
        logger.info("Scheduler stopped.")

    def _print_stats(self) -> None:
        elapsed = time.time() - (self.stats["start_time"] or time.time())
        logger.info("--- Final Stats ---")
        logger.info(f"Elapsed time    : {elapsed:.2f}s")
        logger.info(f"Tasks submitted : {self.stats['tasks_submitted']}")
        logger.info(f"Tasks completed : {self.stats['tasks_completed']}")
        logger.info(f"Tasks failed    : {self.stats['tasks_failed']}")
        logger.info(f"Tasks timed out : {self.stats['tasks_timed_out']}")
        logger.info(f"Agents spawned  : {self.stats['agents_spawned']}")
        logger.info(f"Agents killed   : {self.stats['agents_killed']}")
        logger.info("-------------------")


# ---------------------------------------------------------------------------
# Demo / CLI entrypoint
# ---------------------------------------------------------------------------

def demo():
    """Run a built-in demonstration of the swarm."""
    print("\n" + "=" * 60)
    print("  MASS AGENT SWARM ORCHESTRATOR — DEMO")
    print("=" * 60 + "\n")

    # Custom worker that randomly hangs to test respawn logic
    import random

    def flaky_worker(task: Task) -> Any:
        duration = task.payload.get("duration", 1.0)
        should_hang = task.payload.get("hang", False)
        if should_hang:
            logger.info(f"Task {task.id} INTENTIONALLY HANGING...")
            while True:
                time.sleep(3600)
        time.sleep(duration)
        return {"task_id": task.id, "slept": duration}

    swarm = MassAgentOrchestrator(
        max_agents=6,
        initial_agents=2,
        task_timeout=4.0,       # 4-second timeout so hangs are caught quickly
        heartbeat_interval=2.0,
        worker_fn=flaky_worker,
        auto_scale=True,
    )

    swarm.start()

    # Submit a mix of fast tasks and one hanger
    tasks: List[Task] = []
    for i in range(6):
        tasks.append(Task(payload={"duration": random.uniform(0.3, 1.0)}))
    tasks.append(Task(payload={"hang": True}))   # will be killed & retried
    for i in range(4):
        tasks.append(Task(payload={"duration": random.uniform(0.3, 1.0)}))

    swarm.submit_many(tasks)

    print("Tasks submitted. Waiting for completion...\n")
    swarm.wait_for_completion()
    time.sleep(3)  # Let watchdog clean up stragglers

    print("\n" + "-" * 60)
    print("Status snapshot:")
    print(json.dumps(swarm.status(), indent=2, default=str))
    print("-" * 60)

    swarm.shutdown(wait=False)
    print("\nDemo finished.")


if __name__ == "__main__":
    demo()
