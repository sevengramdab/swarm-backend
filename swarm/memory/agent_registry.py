#!/usr/bin/env python3
"""
agent_registry.py
=================
Live agent registry with full event-sourced history.

ELI5 Analogy:
  Think of this as the employee attendance log and skills roster
  for a construction site. Every worker (agent) signs in with
  their trade skills (capabilities), and every action they take
  — starting a weld, taking a break, finishing a beam — is
  recorded as an immutable entry. The foreman can look back
  through the logbook and see exactly who did what, when, and
  where, even if the worker has already gone home (ephemeral node).
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
from pydantic import BaseModel, Field


class AgentStatus(str, Enum):
    """The worker's current activity state."""
    IDLE = "idle"
    RUNNING = "running"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    TERMINATED = "terminated"


class AgentEvent(BaseModel):
    """One immutable line in the construction site logbook."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent_id: str
    event_type: str  # e.g. "spawned", "task_assigned", "task_completed", "killed", "reallocated"
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)
    node_id: Optional[str] = None


class AgentRecord(BaseModel):
    """The worker's ID badge and current assignment board."""

    agent_id: str
    capabilities: List[str] = Field(default_factory=list)
    node_id: Optional[str] = None
    status: AgentStatus = AgentStatus.IDLE
    current_task: Optional[str] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    spawn_time: float = Field(default_factory=time.time)
    last_heartbeat: float = Field(default_factory=time.time)
    events: List[AgentEvent] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def is_alive(self, timeout: float = 30.0) -> bool:
        """Has the worker checked in recently, or are they MIA?"""
        if self.status in (AgentStatus.OFFLINE, AgentStatus.TERMINATED):
            return False
        return (time.time() - self.last_heartbeat) < timeout


class AgentRegistry:
    """
    The master foreman's clipboard.

    ELI5: Every morning the foreman (AgentRegistry) gets a clipboard
          with every worker's name, trade, and current job. As workers
          sign in, start jobs, or go home, the foreman writes it down
          in permanent ink (event sourcing). If the foreman's trailer
          burns down, a new foreman can rebuild the clipboard from
          the carbon copies (JSONL event log).
    """

    def __init__(self, persist_path: Optional[Path] = None) -> None:
        self.agents: Dict[str, AgentRecord] = {}
        self.events: List[AgentEvent] = []
        self._lock = asyncio.Lock()
        self.persist_path = persist_path or Path("agent_registry.jsonl")
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)

    async def register_agent(
        self,
        agent_id: str,
        capabilities: List[str],
        node_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentRecord:
        """
        ELI5: A new electrician shows up at the site gate.
              The foreman writes their name, trade, and assigned
              trailer (node_id) on the clipboard.
        """
        record = AgentRecord(
            agent_id=agent_id,
            capabilities=capabilities,
            node_id=node_id,
            status=AgentStatus.IDLE,
            metadata=metadata or {},
        )
        event = AgentEvent(
            agent_id=agent_id,
            event_type="spawned",
            payload={"capabilities": capabilities, "node_id": node_id, "metadata": metadata},
            node_id=node_id,
        )
        async with self._lock:
            self.agents[agent_id] = record
            record.events.append(event)
            self.events.append(event)
            await self._append_event(event)
        return record

    async def update_agent_status(
        self,
        agent_id: str,
        status: AgentStatus,
        telemetry: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        ELI5: The electrician radios the foreman: "Finished panel A3,
              moving to A4." The foreman updates the assignment board.
        """
        async with self._lock:
            agent = self.agents.get(agent_id)
            if not agent:
                return False
            agent.status = status
            agent.last_heartbeat = time.time()
            if telemetry:
                agent.metadata.update(telemetry)
            event = AgentEvent(
                agent_id=agent_id,
                event_type="status_update",
                payload={"status": status.value, "telemetry": telemetry},
                node_id=agent.node_id,
            )
            agent.events.append(event)
            self.events.append(event)
            await self._append_event(event)
        return True

    async def assign_task(self, agent_id: str, task_id: str) -> bool:
        """Hand a work order to a specific worker."""
        async with self._lock:
            agent = self.agents.get(agent_id)
            if not agent or agent.status != AgentStatus.IDLE:
                return False
            agent.status = AgentStatus.RUNNING
            agent.current_task = task_id
            agent.last_heartbeat = time.time()
            event = AgentEvent(
                agent_id=agent_id,
                event_type="task_assigned",
                payload={"task_id": task_id},
                node_id=agent.node_id,
            )
            agent.events.append(event)
            self.events.append(event)
            await self._append_event(event)
        return True

    async def complete_task(self, agent_id: str, task_id: str, success: bool = True) -> bool:
        """Mark a work order as finished — update the worker's stats."""
        async with self._lock:
            agent = self.agents.get(agent_id)
            if not agent:
                return False
            agent.current_task = None
            agent.status = AgentStatus.IDLE
            agent.last_heartbeat = time.time()
            if success:
                agent.tasks_completed += 1
            else:
                agent.tasks_failed += 1
            event = AgentEvent(
                agent_id=agent_id,
                event_type="task_completed" if success else "task_failed",
                payload={"task_id": task_id},
                node_id=agent.node_id,
            )
            agent.events.append(event)
            self.events.append(event)
            await self._append_event(event)
        return True

    async def deregister_agent(self, agent_id: str, reason: str = "shutdown") -> bool:
        """
        ELI5: The electrician clocks out and goes home.
              The foreman marks them OFF on the board but keeps
              the logbook entry forever.
        """
        async with self._lock:
            agent = self.agents.get(agent_id)
            if not agent:
                return False
            agent.status = AgentStatus.TERMINATED
            event = AgentEvent(
                agent_id=agent_id,
                event_type="terminated",
                payload={"reason": reason},
                node_id=agent.node_id,
            )
            agent.events.append(event)
            self.events.append(event)
            await self._append_event(event)
        return True

    def get_agent_history(self, agent_id: str) -> List[AgentEvent]:
        """Read the worker's personal logbook from the master archive."""
        agent = self.agents.get(agent_id)
        return agent.events if agent else []

    async def find_capable_agents(
        self,
        required_capabilities: List[str],
        status_filter: Optional[AgentStatus] = None,
    ) -> List[AgentRecord]:
        """
        ELI5: The foreman needs someone who can do both electrical
              AND plumbing. He scans the clipboard for workers with
              both trades who are currently IDLE.
        """
        results: List[AgentRecord] = []
        async with self._lock:
            for agent in self.agents.values():
                if status_filter and agent.status != status_filter:
                    continue
                if agent.status == AgentStatus.TERMINATED:
                    continue
                if all(cap in agent.capabilities for cap in required_capabilities):
                    results.append(agent)
        return results

    async def get_all_agents(self) -> List[AgentRecord]:
        """Return every worker on the clipboard, even the ones on break."""
        async with self._lock:
            return list(self.agents.values())

    async def recover_from_disk(self) -> int:
        """
        ELI5: The foreman's trailer burned down, but the carbon-copy
              logbook was in a fireproof safe. Rebuild the clipboard
              from every line in the log.
        """
        if not self.persist_path.exists():
            return 0

        count = 0
        async with aiofiles.open(self.persist_path, "r", encoding="utf-8") as f:
            async for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    event = AgentEvent(**data)
                    self.events.append(event)
                    # Rebuild agent records from events
                    if event.agent_id not in self.agents:
                        self.agents[event.agent_id] = AgentRecord(
                            agent_id=event.agent_id,
                            events=[event],
                        )
                    else:
                        self.agents[event.agent_id].events.append(event)
                    count += 1
                except Exception:
                    continue
        return count

    async def _append_event(self, event: AgentEvent) -> None:
        """Write one line to the fireproof logbook."""
        line = event.model_dump_json() + "\n"
        async with aiofiles.open(self.persist_path, "a", encoding="utf-8") as f:
            await f.write(line)
