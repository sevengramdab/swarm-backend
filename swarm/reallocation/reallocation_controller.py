"""
Reallocation Controller — like the master smart-home hub mounted by your breaker panel.

It watches every circuit (agent) through its smart meters (bottleneck detector),
notices when an outlet starts flickering or the sub-panel is smoking (stall / VRAM),
and dispatches the moving crew (migration engine) to haul the overloaded appliance
to a different room with emptier circuits.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Dict, List, Optional, Set

from pydantic import BaseModel, Field

from .bottleneck_detector import BottleneckDetector, NodeMetrics, PressureLevel, ResourceType
from .execution_graph import ExecutionGraph, GraphBuilder, TaskNode, TaskStatus
from .migration_engine import MigrationEngine, MigrationResult, PeerInfo

logger = logging.getLogger("simplepod.reallocation")


class AgentHeartbeat(BaseModel):
    """
    A chirp from a smart outlet saying: 'I'm still here, here's my current draw.'
    """

    agent_id: str
    timestamp: float = Field(default_factory=time.time)
    tasks_running: List[str] = Field(default_factory=list)
    vram_used_bytes: int = Field(default=0, ge=0)
    vram_total_bytes: int = Field(default=1, ge=1)
    cpu_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    network_in_mbps: float = Field(default=0.0, ge=0.0)
    network_out_mbps: float = Field(default=0.0, ge=0.0)


class StallRecord(BaseModel):
    """
    A sticky note on the fridge: 'Garage freezer stopped humming at 2:14 PM.'
    """

    agent_id: str
    task_id: str
    detected_at: float = Field(default_factory=time.time)
    reason: str = Field(default="")
    reallocated: bool = Field(default=False)


class ReallocationPolicy(BaseModel):
    """
    The house rules posted on the bulletin board.
    """

    max_retries: int = Field(default=3, ge=0)
    """How many times we try to flip a breaker before we call an electrician."""

    stall_timeout_sec: float = Field(default=30.0, ge=1.0)
    """How long an outlet can sit silent before we assume it's broken."""

    vram_red_threshold: float = Field(default=0.95, ge=0.0, le=1.0)
    """If the memory closet is 95%% full, it's time to move boxes to the attic."""

    cooldown_sec: float = Field(default=10.0, ge=0.0)
    """How long we wait between calling the movers, so we don't spam them."""

    auto_migrate: bool = Field(default=True)
    """If False, we only ring the alarm bell and let a human flip the switch."""


class ReallocationController:
    """
    The brain of the smart home.

    It never sleeps, it reads every meter, it knows every wire,
    and it will calmly reroute power before your Christmas tree
    browns out the neighborhood.
    """

    def __init__(
        self,
        controller_id: str,
        policy: Optional[ReallocationPolicy] = None,
    ) -> None:
        """
        Mount the hub on the wall, plug it into the panel, and set the house rules.
        """
        self.controller_id = controller_id
        self.policy = policy or ReallocationPolicy()
        self.detector = BottleneckDetector(
            vram_red_threshold=self.policy.vram_red_threshold,
        )
        self.engine: Optional[MigrationEngine] = None
        self._graph: Optional[ExecutionGraph] = None
        self._builder: Optional[GraphBuilder] = None

        self._agents: Dict[str, AgentHeartbeat] = {}
        self._stalls: Dict[str, StallRecord] = {}
        self._last_migration_time: Dict[str, float] = {}
        self._shutdown_event = asyncio.Event()
        self._monitor_task: Optional[asyncio.Task[None]] = None
        self._callbacks: List[Callable[[str, MigrationResult], None]] = []
        self._lock = asyncio.Lock()

    def attach_engine(self, engine: MigrationEngine) -> None:
        """
        Introduce the moving company to the smart home hub.
        Now the hub can actually call vans when it spots trouble.
        """
        self.engine = engine

    def attach_graph(self, graph: ExecutionGraph) -> None:
        """
        Hang the house blueprint on the wall next to the hub.
        """
        self._graph = graph

    def attach_builder(self, builder: GraphBuilder) -> None:
        """
        Keep the contractor on speed-dial so we can add new outlets mid-renovation.
        """
        self._builder = builder

    def on_reallocation(self, callback: Callable[[str, MigrationResult], None]) -> None:
        """
        Wire a doorbell to the hub so a human gets notified every time we move an appliance.
        """
        self._callbacks.append(callback)

    async def register_agent(self, heartbeat: AgentHeartbeat) -> None:
        """
        A new smart outlet just checked in and said hello.
        We file its business card and start watching its meter.
        """
        async with self._lock:
            self._agents[heartbeat.agent_id] = heartbeat

        metrics = NodeMetrics(
            node_id=heartbeat.agent_id,
            gpu_util_percent=0.0,  # Simplified — could derive from tasks.
            vram_used_bytes=heartbeat.vram_used_bytes,
            vram_total_bytes=heartbeat.vram_total_bytes,
            cpu_percent=heartbeat.cpu_percent,
            network_in_mbps=heartbeat.network_in_mbps,
            network_out_mbps=heartbeat.network_out_mbps,
        )
        await self.detector.record(metrics)

        # If the engine knows this peer, refresh it.
        if self.engine:
            peer = PeerInfo(
                peer_id=heartbeat.agent_id,
                host="dynamic",
                port=0,
                healthy=True,
                vram_free_bytes=max(0, heartbeat.vram_total_bytes - heartbeat.vram_used_bytes),
                cpu_free_cores=max(0.0, 100.0 - heartbeat.cpu_percent) / 100.0 * 8.0,  # Assume 8-core baseline.
                latency_ms=5.0,
            )
            await self.engine.add_peer(peer)

    async def unregister_agent(self, agent_id: str) -> None:
        """
        An outlet went permanently dark — maybe the breaker fried.
        We pull its card and immediately flag every task it was running as stalled.
        """
        async with self._lock:
            self._agents.pop(agent_id, None)

        if self._graph:
            for node in self._graph.nodes.values():
                if node.agent_id == agent_id and node.status == TaskStatus.RUNNING:
                    node.status = TaskStatus.STALLED
                    self._stalls[node.task_id] = StallRecord(
                        agent_id=agent_id,
                        task_id=node.task_id,
                        reason="Parent outlet lost power — agent vanished.",
                    )

        if self.engine:
            await self.engine.remove_peer(agent_id)

    async def _detect_stalls(self) -> List[StallRecord]:
        """
        Walk the house with a flashlight, listening for buzzing outlets.

        If an outlet says it's RUNNING but its meter hasn't ticked in a while,
        or the whole room is silent, we slap a 'STALLED' sticky note on it.
        """
        new_stalls: List[StallRecord] = []
        if not self._graph:
            return new_stalls

        for node in self._graph.nodes.values():
            if node.status != TaskStatus.RUNNING:
                continue
            agent_id = node.agent_id
            if not agent_id:
                continue

            # Check GPU stall (VRAM flatline).
            stalled_gpu, reason_gpu = await self.detector.is_stalled(
                agent_id, ResourceType.GPU, stall_threshold_sec=self.policy.stall_timeout_sec
            )
            stalled_cpu, reason_cpu = await self.detector.is_stalled(
                agent_id, ResourceType.CPU, stall_threshold_sec=self.policy.stall_timeout_sec
            )

            if stalled_gpu or stalled_cpu:
                record = StallRecord(
                    agent_id=agent_id,
                    task_id=node.task_id,
                    reason=reason_gpu or reason_cpu or "Unknown flatline.",
                )
                async with self._lock:
                    if node.task_id not in self._stalls:
                        self._stalls[node.task_id] = record
                        node.status = TaskStatus.STALLED
                        new_stalls.append(record)
                        logger.warning(
                            "Stall detected — outlet %s in room %s: %s",
                            node.task_id, agent_id, record.reason,
                        )
        return new_stalls

    async def _detect_vram_pressure(self) -> List[str]:
        """
        Read every sub-panel's VRAM meter and list the rooms that are bursting at the seams.

        Like walking into the attic and seeing storage boxes stacked to the rafters —
        time to rent a storage unit (migrate to another node).
        """
        hot = await self.detector.hot_nodes(min_level=PressureLevel.ORANGE)
        return hot

    async def _pick_relocation_target(self, task: TaskNode) -> Optional[str]:
        """
        Call every moving company in the rolodex and ask who has a truck big enough.

        We need a peer with enough empty closet space (VRAM) and enough free circuits (CPU)
        to handle this appliance without immediately overloading.
        """
        if not self.engine:
            return None
        target = await self.engine.select_target(
            required_vram=task.resources.vram_bytes,
            required_cpu=task.resources.cpu_cores,
            exclude_nodes=[task.agent_id] if task.agent_id else [],
        )
        return target.peer_id if target else None

    async def _execute_reallocation(
        self,
        task_id: str,
        reason: str,
    ) -> MigrationResult:
        """
        The actual moment the moving crew shows up.

        We bubble-wrap the appliance, load it on the van, drive it to the new house,
        and wait for a signature. If the van crashes, we mark the task FAILED
        and ring the alarm bells.
        """
        if not self._graph or not self.engine:
            return MigrationResult(
                success=False,
                task_id=task_id,
                source_node="unknown",
                target_node="unknown",
                message="No blueprint or moving company available.",
            )

        task = self._graph.nodes.get(task_id)
        if not task:
            return MigrationResult(
                success=False,
                task_id=task_id,
                source_node="unknown",
                target_node="unknown",
                message="Task not found on blueprint.",
            )

        source_node = task.agent_id or self.controller_id
        target_node = await self._pick_relocation_target(task)

        if not target_node:
            task.status = TaskStatus.FAILED
            return MigrationResult(
                success=False,
                task_id=task_id,
                source_node=source_node,
                target_node="unknown",
                message="No moving company has a truck big enough right now.",
            )

        # Pack and encrypt.
        try:
            payload = await self.engine.pack_payload(self._graph, task_id)
            encrypted = await self.engine.encrypt_payload(payload)
        except Exception as exc:
            task.status = TaskStatus.FAILED
            return MigrationResult(
                success=False,
                task_id=task_id,
                source_node=source_node,
                target_node=target_node,
                message=f"Packing failed: {exc}",
            )

        # Update local state to migrating.
        task.status = TaskStatus.MIGRATING
        task.agent_id = None  # In transit.

        # Ship it.
        result = await self.engine.send_migration(target_node, encrypted)

        if result.success:
            task.agent_id = target_node
            task.status = TaskStatus.PENDING  # Ready to resume on new node.
            async with self._lock:
                self._last_migration_time[task_id] = time.time()
                if task_id in self._stalls:
                    self._stalls[task_id].reallocated = True
            logger.info(
                "Reallocation OK — moved outlet %s from %s to %s in %.2fs: %s",
                task_id, source_node, target_node, result.duration_sec, result.message,
            )
        else:
            task.status = TaskStatus.FAILED
            logger.error(
                "Reallocation FAILED — outlet %s from %s to %s: %s",
                task_id, source_node, target_node, result.message,
            )

        for cb in self._callbacks:
            try:
                cb(task_id, result)
            except Exception:
                pass

        return result

    async def _tick(self) -> None:
        """
        One full sweep of the house: read meters, check for stalls, move boxes if needed.

        Like the smart hub's nightly routine: check every door lock,
        every smoke detector, and every thermostat — then act if anything's off.
        """
        # 1) Detect stalls.
        stalls = await self._detect_stalls()

        # 2) Detect VRAM pressure.
        hot_nodes = await self._detect_vram_pressure()

        # 3) Build relocation queue.
        relocate_queue: List[Tuple[str, str]] = []
        now = time.time()

        # Stalled tasks first — they're actively broken.
        for record in stalls:
            last_move = self._last_migration_time.get(record.task_id, 0.0)
            if now - last_move < self.policy.cooldown_sec:
                continue
            relocate_queue.append((record.task_id, record.reason))

        # Then VRAM-hot nodes: move their biggest tasks.
        if self._graph:
            for node in self._graph.nodes.values():
                if node.status != TaskStatus.RUNNING:
                    continue
                if node.agent_id not in hot_nodes:
                    continue
                last_move = self._last_migration_time.get(node.task_id, 0.0)
                if now - last_move < self.policy.cooldown_sec:
                    continue
                relocate_queue.append((
                    node.task_id,
                    f"VRAM pressure on node {node.agent_id} — attic is full.",
                ))

        if not relocate_queue or not self.policy.auto_migrate:
            return

        # 4) Execute migrations one at a time to avoid chaos.
        for task_id, reason in relocate_queue:
            await self._execute_reallocation(task_id, reason)
            # Small pause between moves so we don't swamp the movers.
            await asyncio.sleep(0.5)

    async def start_monitoring(self, interval_sec: float = 5.0) -> None:
        """
        Flip the smart hub to ON and tell it to check the house every few seconds.

        Like programming your Nest to poll every temperature sensor
        and call the HVAC company if the attic hits 120°F.
        """
        if self._monitor_task is not None:
            return
        self._shutdown_event.clear()

        async def _loop() -> None:
            while not self._shutdown_event.is_set():
                try:
                    await self._tick()
                except Exception as exc:
                    logger.exception("Monitoring sweep crashed: %s", exc)
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=interval_sec)
                except asyncio.TimeoutError:
                    pass

        self._monitor_task = asyncio.create_task(_loop())
        logger.info("Smart hub monitoring started — checking every %.1f seconds.", interval_sec)

    async def stop_monitoring(self) -> None:
        """
        Hit the big red OFF button on the smart hub.
        It finishes its current sweep, then goes to sleep.
        """
        self._shutdown_event.set()
        if self._monitor_task:
            try:
                await asyncio.wait_for(self._monitor_task, timeout=10.0)
            except asyncio.TimeoutError:
                self._monitor_task.cancel()
                try:
                    await self._monitor_task
                except asyncio.CancelledError:
                    pass
            self._monitor_task = None
        logger.info("Smart hub monitoring stopped.")

    async def force_reallocate(self, task_id: str) -> MigrationResult:
        """
        The human hits the panic button.

        Like running to the breaker panel and manually flipping a switch
        because you smell smoke — no questions asked, just move it NOW.
        """
        return await self._execute_reallocation(task_id, "Forced by manual override.")

    async def get_status(self) -> Dict[str, Any]:
        """
        Ask the hub for a full diagnostic printout.

        Like opening your smart-home app and seeing every room's temperature,
        every lock's battery, and every motion sensor's last ping.
        """
        async with self._lock:
            agents = dict(self._agents)
            stalls = dict(self._stalls)

        forecasts = await self.detector.analyze_all()
        return {
            "controller_id": self.controller_id,
            "agents_registered": len(agents),
            "agents": {aid: hb.model_dump(mode="json") for aid, hb in agents.items()},
            "stalls_detected": len(stalls),
            "stalls": {sid: s.model_dump(mode="json") for sid, s in stalls.items()},
            "forecasts": {
                nid: [f.model_dump(mode="json") for f in fs]
                for nid, fs in forecasts.items()
            },
            "policy": self.policy.model_dump(mode="json"),
        }

    async def drain_and_exit(self) -> None:
        """
        The family is moving out. Finish all in-flight jobs, then pull the plug.

        Like telling the movers: 'Deliver everything still in the trucks,
        then come back to the warehouse and clock out.'
        """
        await self.stop_monitoring()
        if self._graph:
            running = [
                n for n in self._graph.nodes.values()
                if n.status in (TaskStatus.RUNNING, TaskStatus.MIGRATING)
            ]
            if running:
                logger.info("Waiting for %d in-flight tasks to land...", len(running))
                for _ in range(60):
                    still = [
                        n for n in self._graph.nodes.values()
                        if n.status in (TaskStatus.RUNNING, TaskStatus.MIGRATING)
                    ]
                    if not still:
                        break
                    await asyncio.sleep(1.0)
        logger.info("Reallocation controller drained and powered off.")
