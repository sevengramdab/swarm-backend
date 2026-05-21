"""
Execution Graph — like a house's electrical panel diagram.

Every task is an outlet, every dependency is a wire running between outlets.
Before you flip a breaker (migrate a task), you must know which wires are connected
or you'll leave half the house in the dark.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional, Set

from pydantic import BaseModel, Field, field_validator


class TaskStatus(str, Enum):
    """
    Like the states of a smart light switch in your home.
    """

    PENDING = "pending"          # Bulb is off, waiting for someone to flip the switch.
    RUNNING = "running"          # Bulb is glowing, electricity is flowing.
    STALLED = "stalled"          # Bulb flickered and died — probably a bad wire.
    COMPLETED = "completed"      # Bulb did its job and turned off on schedule.
    MIGRATING = "migrating"      # You're unscrewing the bulb to move it to another room.
    FAILED = "failed"            # The breaker tripped; something went very wrong.


class ResourceProfile(BaseModel):
    """
    Like the sticker on the back of your appliances that says how many watts they draw.
    """

    vram_bytes: int = Field(default=0, ge=0)
    """How much GPU memory this appliance wants, in bytes. Like a space heater sucking watts."""

    cpu_cores: float = Field(default=0.0, ge=0.0)
    """How many CPU cores this appliance needs. Like how many 20-amp circuits it wants."""

    network_mbps: float = Field(default=0.0, ge=0.0)
    """How much internet bandwidth this gadget eats, in megabits per second."""

    disk_bytes: int = Field(default=0, ge=0)
    """How much closet space (disk) this gadget's box needs, in bytes."""


class TaskNode(BaseModel):
    """
    A single smart outlet in your house's automation system.
    It has a name, knows what power it needs, and remembers which other outlets it depends on.
    """

    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    """The unique serial number etched on the outlet plate."""

    name: str = Field(default="unnamed_task")
    """The friendly label you wrote with a Sharpie, like 'Kitchen Lights'."""

    status: TaskStatus = Field(default=TaskStatus.PENDING)
    """What the outlet is doing right now — off, on, flickering, etc."""

    agent_id: Optional[str] = Field(default=None)
    """Which circuit breaker panel (agent) this outlet is currently wired to."""

    resources: ResourceProfile = Field(default_factory=ResourceProfile)
    """The wattage sticker for this outlet's appliance."""

    dependencies: Set[str] = Field(default_factory=set)
    """Other outlets that must be 'on' before this one can turn on.
    Like making sure the porch light works before you install the motion sensor."""

    payload_digest: Optional[str] = Field(default=None)
    """A fingerprint of the package plugged into this outlet.
    Helps us know if someone swapped the toaster for a blender."""

    created_at: datetime = Field(default_factory=datetime.utcnow)
    """The moment you installed this outlet in the wall."""

    started_at: Optional[datetime] = Field(default=None)
    """The moment you first flipped this outlet's switch."""

    completed_at: Optional[datetime] = Field(default=None)
    """The moment this outlet finished its job and went dark."""

    metadata: Dict[str, Any] = Field(default_factory=dict)
    """Sticky notes you left on the outlet — colors, brands, whatever."""

    @field_validator("dependencies", mode="before")
    @classmethod
    def _coerce_deps(cls, v: Any) -> Set[str]:
        """
        Like making sure your list of 'rooms to wire first' is actually a list,
        not a single string or None.
        """
        if v is None:
            return set()
        if isinstance(v, str):
            return {v}
        if isinstance(v, list):
            return set(v)
        return set(v)

    def is_ready(self, completed_ids: Set[str]) -> bool:
        """
        Can we flip this switch yet?

        Like checking if all the upstream GFCI outlets have reset
        before you plug in the hair dryer.
        """
        return self.dependencies.issubset(completed_ids)

    def to_snapshot(self) -> TaskSnapshot:
        """
        Take a Polaroid of this outlet so we can rebuild it exactly
        on another wall if we need to move it.
        """
        return TaskSnapshot(
            task_id=self.task_id,
            name=self.name,
            status=self.status,
            agent_id=self.agent_id,
            resources=self.resources.model_copy(),
            dependencies=set(self.dependencies),
            payload_digest=self.payload_digest,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            metadata=dict(self.metadata),
        )


class TaskSnapshot(BaseModel):
    """
    A Polaroid photo of an outlet at a specific moment.
    Flat, simple, and safe to mail across town.
    """

    task_id: str
    name: str
    status: TaskStatus
    agent_id: Optional[str]
    resources: ResourceProfile
    dependencies: Set[str]
    payload_digest: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    metadata: Dict[str, Any]


class ExecutionGraph(BaseModel):
    """
    The master blueprint of every outlet, switch, and wire in the house.
    Before the electrician (migration engine) touches anything,
    they study this drawing.
    """

    graph_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    """The blueprint's serial number."""

    nodes: Dict[str, TaskNode] = Field(default_factory=dict)
    """All the outlets in the house, looked up by their serial numbers."""

    @field_validator("nodes", mode="before")
    @classmethod
    def _coerce_nodes(cls, v: Any) -> Dict[str, TaskNode]:
        """
        If someone hands us a list of outlets, organize them into a cabinet
        sorted by serial number so we can find them fast.
        """
        if isinstance(v, list):
            return {n.task_id: n for n in v}
        return v

    def add_node(self, node: TaskNode) -> None:
        """
        Screw a new outlet into the wall and add it to the blueprint.
        """
        self.nodes[node.task_id] = node

    def remove_node(self, task_id: str) -> Optional[TaskNode]:
        """
        Unscrew an outlet from the wall and yank it out of the blueprint.
        Returns the old outlet, or None if it was already gone.
        """
        return self.nodes.pop(task_id, None)

    def get_ready_tasks(self) -> List[TaskNode]:
        """
        Look at every outlet and ask: 'Are all your upstream wires hot?'
        Return only the ones that are safe to flip right now.
        """
        completed: Set[str] = {
            tid for tid, n in self.nodes.items() if n.status == TaskStatus.COMPLETED
        }
        return [
            n for n in self.nodes.values()
            if n.status == TaskStatus.PENDING and n.is_ready(completed)
        ]

    def get_dependents(self, task_id: str) -> List[TaskNode]:
        """
        Find every outlet downstream from this one.
        Like tracing a wire from the breaker to see which lights go dark
        if you cut power here.
        """
        return [
            n for n in self.nodes.values()
            if task_id in n.dependencies
        ]

    def topological_order(self) -> List[str]:
        """
        Figure out the exact order to flip switches so nothing explodes.

        Like planning your morning: coffee maker before blender,
        because the blender wakes you up but the coffee keeps you alive.
        """
        in_degree: Dict[str, int] = {tid: 0 for tid in self.nodes}
        for node in self.nodes.values():
            for dep in node.dependencies:
                if dep in in_degree:
                    in_degree[node.task_id] += 1

        queue: List[str] = [tid for tid, deg in in_degree.items() if deg == 0]
        order: List[str] = []

        while queue:
            current = queue.pop(0)
            order.append(current)
            for dep_id in [n.task_id for n in self.get_dependents(current)]:
                in_degree[dep_id] -= 1
                if in_degree[dep_id] == 0:
                    queue.append(dep_id)

        if len(order) != len(self.nodes):
            raise ValueError("Cycle detected in execution graph — like a light switch wired to turn itself off and on forever.")
        return order

    def to_snapshot(self) -> GraphSnapshot:
        """
        Photocopy the entire blueprint, every outlet, every wire,
        so we can mail it to another electrician across town.
        """
        return GraphSnapshot(
            graph_id=self.graph_id,
            nodes=[n.to_snapshot() for n in self.nodes.values()],
        )

    @classmethod
    def from_snapshot(cls, snapshot: GraphSnapshot) -> ExecutionGraph:
        """
        Receive a photocopied blueprint in the mail and rebuild the entire house exactly.
        """
        graph = cls(graph_id=snapshot.graph_id)
        for snap in snapshot.nodes:
            graph.add_node(TaskNode(
                task_id=snap.task_id,
                name=snap.name,
                status=snap.status,
                agent_id=snap.agent_id,
                resources=snap.resources,
                dependencies=set(snap.dependencies),
                payload_digest=snap.payload_digest,
                created_at=snap.created_at,
                started_at=snap.started_at,
                completed_at=snap.completed_at,
                metadata=snap.metadata,
            ))
        return graph


class GraphSnapshot(BaseModel):
    """
    A flat envelope containing photocopies of every outlet in the house.
    No pointers, no live wires — just paper and ink, safe to ship anywhere.
    """

    graph_id: str
    nodes: List[TaskSnapshot]


class GraphBuilder:
    """
    A friendly contractor who helps you draw blueprints without getting shocked.
    """

    def __init__(self) -> None:
        """
        Hand the contractor an empty clipboard.
        """
        self._graph = ExecutionGraph()
        self._lock = asyncio.Lock()

    async def add_task(
        self,
        name: str,
        resources: Optional[ResourceProfile] = None,
        dependencies: Optional[Set[str]] = None,
        agent_id: Optional[str] = None,
        payload_digest: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskNode:
        """
        Tell the contractor to install a new smart outlet.

        Like saying: 'Put a dimmer in the dining room,
        it needs 60 watts, and don't turn it on until the foyer light is ready.'
        """
        async with self._lock:
            node = TaskNode(
                name=name,
                resources=resources or ResourceProfile(),
                dependencies=dependencies or set(),
                agent_id=agent_id,
                payload_digest=payload_digest,
                metadata=metadata or {},
            )
            self._graph.add_node(node)
            return node

    async def add_dependency(self, task_id: str, depends_on: str) -> None:
        """
        Run a new wire between two outlets.

        Like telling the contractor: 'The porch motion sensor
        must not turn on until the front floodlight is working.'
        """
        async with self._lock:
            if task_id not in self._graph.nodes:
                raise KeyError(f"Outlet {task_id} doesn't exist on the blueprint yet.")
            if depends_on not in self._graph.nodes:
                raise KeyError(f"Upstream outlet {depends_on} doesn't exist on the blueprint yet.")
            self._graph.nodes[task_id].dependencies.add(depends_on)

    async def build(self) -> ExecutionGraph:
        """
        The contractor hands you the finished blueprint and goes home.
        """
        async with self._lock:
            return self._graph.model_copy(deep=True)
