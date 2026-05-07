"""
Swarm State Manager — Live circuit tracking for the Command Viewport Dashboard.
Tracks agent trees, task checklists, thought streams, and telemetry sparklines.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class TaskItem:
    task_id: str
    description: str
    status: str = "queued"  # queued | active | committed
    progress_pct: float = 0.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "status": self.status,
            "progress_pct": self.progress_pct,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class TelemetryPoint:
    input_tokens: int
    output_tokens: int
    timestamp: float


@dataclass
class TelemetrySparkline:
    max_points: int = 60
    data: List[TelemetryPoint] = field(default_factory=list)

    def add(self, input_tokens: int, output_tokens: int):
        self.data.append(TelemetryPoint(input_tokens, output_tokens, time.time()))
        if len(self.data) > self.max_points:
            self.data = self.data[-self.max_points:]

    def to_dict(self) -> dict:
        return {
            "input_tokens": [d.input_tokens for d in self.data],
            "output_tokens": [d.output_tokens for d in self.data],
            "timestamps": [d.timestamp for d in self.data],
        }


@dataclass
class AgentNode:
    agent_id: str
    parent_id: Optional[str]
    session_id: str
    role: str
    name: str
    status: str = "queued"  # queued | active | idle | paused | error | committed
    system_prompt: str = ""
    thought_stream: List[dict] = field(default_factory=list)
    tasks: List[TaskItem] = field(default_factory=list)
    telemetry: TelemetrySparkline = field(default_factory=TelemetrySparkline)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    max_thoughts: int = 200

    def append_thought(self, thought_type: str, content: str):
        self.thought_stream.append({
            "timestamp": time.time(),
            "type": thought_type,
            "content": content,
        })
        if len(self.thought_stream) > self.max_thoughts:
            self.thought_stream = self.thought_stream[-self.max_thoughts:]
        self.updated_at = time.time()

    def add_task(self, description: str, task_id: Optional[str] = None) -> TaskItem:
        task = TaskItem(
            task_id=task_id or f"task-{uuid.uuid4().hex[:8]}",
            description=description,
        )
        self.tasks.append(task)
        self.updated_at = time.time()
        return task

    def update_task(self, task_id: str, status: Optional[str] = None, progress_pct: Optional[float] = None):
        for task in self.tasks:
            if task.task_id == task_id:
                if status is not None:
                    task.status = status
                if progress_pct is not None:
                    task.progress_pct = max(0.0, min(100.0, progress_pct))
                task.updated_at = time.time()
                self.updated_at = time.time()
                return True
        return False

    def set_status(self, status: str):
        self.status = status
        self.updated_at = time.time()

    def to_dict(self, include_thoughts: bool = True) -> dict:
        d = {
            "agent_id": self.agent_id,
            "parent_id": self.parent_id,
            "session_id": self.session_id,
            "role": self.role,
            "name": self.name,
            "status": self.status,
            "system_prompt": self.system_prompt,
            "tasks": [t.to_dict() for t in self.tasks],
            "telemetry": self.telemetry.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if include_thoughts:
            d["thought_stream"] = self.thought_stream
        else:
            d["thought_stream_count"] = len(self.thought_stream)
        return d


class SwarmStateManager:
    """Global singleton tracking all swarm agent trees and their live state."""

    def __init__(self):
        self._agents: Dict[str, AgentNode] = {}
        self._session_roots: Dict[str, str] = {}  # session_id -> root agent_id
        self._children: Dict[str, List[str]] = {}  # parent_id -> [child_agent_ids]
        self._ws_connections: Dict[str, List[Any]] = {}  # session_id -> [websockets]
        self._lock = asyncio.Lock()

    # ── Agent Lifecycle ──

    def create_swarm(self, session_id: str, task: str) -> AgentNode:
        """Initialize a new swarm with a root orchestrator node."""
        root_id = f"root-{uuid.uuid4().hex[:8]}"
        root = AgentNode(
            agent_id=root_id,
            parent_id=None,
            session_id=session_id,
            role="orchestrator",
            name="Orchestrator",
            status="active",
            system_prompt=f"Orchestrating swarm for task: {task}",
        )
        self._agents[root_id] = root
        self._session_roots[session_id] = root_id
        self._children[root_id] = []
        return root

    def spawn_agent(self, parent_id: str, role: str, name: str, system_prompt: str = "") -> AgentNode:
        """Spawn a child agent under a parent."""
        agent_id = f"{role}-{uuid.uuid4().hex[:8]}"
        parent = self._agents.get(parent_id)
        session_id = parent.session_id if parent else "unknown"
        agent = AgentNode(
            agent_id=agent_id,
            parent_id=parent_id,
            session_id=session_id,
            role=role,
            name=name,
            status="queued",
            system_prompt=system_prompt,
        )
        self._agents[agent_id] = agent
        if parent_id not in self._children:
            self._children[parent_id] = []
        self._children[parent_id].append(agent_id)
        self._children[agent_id] = []
        return agent

    def get_agent(self, agent_id: str) -> Optional[AgentNode]:
        return self._agents.get(agent_id)

    def get_root(self, session_id: str) -> Optional[AgentNode]:
        root_id = self._session_roots.get(session_id)
        if root_id:
            return self._agents.get(root_id)
        return None

    def remove_swarm(self, session_id: str):
        """Clean up all agents for a session."""
        root_id = self._session_roots.pop(session_id, None)
        if not root_id:
            return
        to_remove = [root_id]
        queue = [root_id]
        while queue:
            pid = queue.pop(0)
            for cid in self._children.get(pid, []):
                to_remove.append(cid)
                queue.append(cid)
        for aid in to_remove:
            self._agents.pop(aid, None)
            self._children.pop(aid, None)
        self._ws_connections.pop(session_id, None)

    # ── Tree Serialization ──

    def get_tree(self, session_id: str) -> Optional[dict]:
        root = self.get_root(session_id)
        if not root:
            return None
        return self._build_tree_node(root.agent_id)

    def _build_tree_node(self, agent_id: str) -> dict:
        agent = self._agents.get(agent_id)
        if not agent:
            return {}
        node = agent.to_dict(include_thoughts=False)
        node["children"] = [self._build_tree_node(cid) for cid in self._children.get(agent_id, [])]
        return node

    def get_agent_detail(self, agent_id: str) -> Optional[dict]:
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        return agent.to_dict(include_thoughts=True)

    def get_session_agents(self, session_id: str) -> List[AgentNode]:
        return [a for a in self._agents.values() if a.session_id == session_id]

    # ── State Mutations ──

    def update_agent_status(self, agent_id: str, status: str):
        agent = self._agents.get(agent_id)
        if agent:
            agent.set_status(status)

    def append_thought(self, agent_id: str, thought_type: str, content: str):
        agent = self._agents.get(agent_id)
        if agent:
            agent.append_thought(thought_type, content)

    def update_task(self, agent_id: str, task_id: str, status: Optional[str] = None, progress_pct: Optional[float] = None):
        agent = self._agents.get(agent_id)
        if agent:
            agent.update_task(task_id, status, progress_pct)

    def add_task(self, agent_id: str, description: str, task_id: Optional[str] = None) -> Optional[TaskItem]:
        agent = self._agents.get(agent_id)
        if agent:
            return agent.add_task(description, task_id)
        return None

    def add_telemetry(self, agent_id: str, input_tokens: int, output_tokens: int):
        agent = self._agents.get(agent_id)
        if agent:
            agent.telemetry.add(input_tokens, output_tokens)

    # ── Circuit Summary ──

    def get_circuit_status(self, session_id: str) -> dict:
        agents = self.get_session_agents(session_id)
        if not agents:
            return {"overall": "offline", "bottleneck": None, "agent_count": 0}
        statuses = [a.status for a in agents]
        if any(s == "error" for s in statuses):
            overall = "error"
        elif any(s == "paused" for s in statuses):
            overall = "paused"
        elif any(s == "active" for s in statuses):
            overall = "active"
        elif all(s == "committed" for s in statuses):
            overall = "committed"
        else:
            overall = "idle"
        # Bottleneck = deepest active agent
        bottleneck = None
        max_depth = -1
        for a in agents:
            if a.status == "active":
                depth = self._agent_depth(a.agent_id)
                if depth > max_depth:
                    max_depth = depth
                    bottleneck = a.to_dict(include_thoughts=False)
        return {
            "overall": overall,
            "bottleneck": bottleneck,
            "agent_count": len(agents),
            "status_breakdown": {
                "queued": statuses.count("queued"),
                "active": statuses.count("active"),
                "idle": statuses.count("idle"),
                "paused": statuses.count("paused"),
                "error": statuses.count("error"),
                "committed": statuses.count("committed"),
            },
        }

    def _agent_depth(self, agent_id: str) -> int:
        depth = 0
        agent = self._agents.get(agent_id)
        while agent and agent.parent_id:
            depth += 1
            agent = self._agents.get(agent.parent_id)
        return depth

    # ── WebSocket Pub/Sub ──

    async def subscribe_ws(self, session_id: str, websocket: Any):
        async with self._lock:
            if session_id not in self._ws_connections:
                self._ws_connections[session_id] = []
            self._ws_connections[session_id].append(websocket)
        # Send initial snapshot
        tree = self.get_tree(session_id)
        circuit = self.get_circuit_status(session_id)
        try:
            await websocket.send_json({
                "type": "init",
                "tree": tree,
                "circuit": circuit,
            })
        except Exception:
            pass

    async def unsubscribe_ws(self, session_id: str, websocket: Any):
        async with self._lock:
            conns = self._ws_connections.get(session_id, [])
            if websocket in conns:
                conns.remove(websocket)

    async def broadcast(self, session_id: str, event: dict):
        """Broadcast an event to all connected WebSockets for a session."""
        async with self._lock:
            conns = list(self._ws_connections.get(session_id, []))
        dead = []
        for ws in conns:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    if ws in self._ws_connections.get(session_id, []):
                        self._ws_connections[session_id].remove(ws)

    async def broadcast_agent_update(self, session_id: str, agent_id: str):
        agent = self.get_agent(agent_id)
        if not agent:
            return
        await self.broadcast(session_id, {
            "type": "agent_update",
            "agent": agent.to_dict(include_thoughts=False),
        })

    async def broadcast_thought(self, session_id: str, agent_id: str, thought_type: str, content: str):
        await self.broadcast(session_id, {
            "type": "thought",
            "agent_id": agent_id,
            "thought": {
                "timestamp": time.time(),
                "type": thought_type,
                "content": content,
            },
        })

    async def broadcast_task_update(self, session_id: str, agent_id: str, task: TaskItem):
        await self.broadcast(session_id, {
            "type": "task_update",
            "agent_id": agent_id,
            "task": task.to_dict(),
        })

    async def broadcast_telemetry(self, session_id: str, agent_id: str, telemetry: TelemetrySparkline):
        await self.broadcast(session_id, {
            "type": "telemetry",
            "agent_id": agent_id,
            "telemetry": telemetry.to_dict(),
        })

    async def broadcast_circuit(self, session_id: str):
        circuit = self.get_circuit_status(session_id)
        await self.broadcast(session_id, {
            "type": "circuit_update",
            "circuit": circuit,
        })


# Global singleton
state_manager = SwarmStateManager()
