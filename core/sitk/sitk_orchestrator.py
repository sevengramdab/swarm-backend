"""
Self-Installing Tool-Kit (SITK) Orchestrator

Master control plane: picks a node, stages payload, watches execution, fetches results.
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

# Import sibling modules (relative imports work inside the simplepod_swarm package).
from .sitk_packager import build_payload, PayloadConfig, TaskDefinition
from .sitk_deployer import deploy_local, deploy_ssh, NodeCredentials, DeployResult, TransferProgress
from .sitk_executor import ExecutorConfig


try:
    import asyncssh

    HAS_ASYNCSSH = True
except ImportError:
    HAS_ASYNCSSH = False


# =============================================================================
# Pydantic Models
# =============================================================================

# ELI5: Like a digital Rolodex card for each house in the neighborhood
#       that tracks whether the power is on, if the owner is home, and
#       how many jobs they've had done before.
class NodeDescriptor(BaseModel):
    """Everything the orchestrator knows about one worker node."""

    node_id: str
    host: str
    port: int = 22
    username: str = "simplepod"
    password: Optional[str] = None
    private_key_path: Optional[Path] = None
    capabilities: List[str] = Field(default_factory=list)
    max_tasks: int = Field(default=4, ge=1)
    current_tasks: int = 0
    healthy: bool = True
    last_seen: Optional[str] = None
    labels: Dict[str, str] = Field(default_factory=dict)
    is_local: bool = False


# ELI5: Like the clipboard handed to the driver that gets updated
#       at every stop: picked up, on the road, delivered, signed-for.
class LifecycleHandle(BaseModel):
    """Mutable tracking object for one payload's journey."""

    payload_id: str
    node_id: str
    payload_path: Optional[Path] = None
    deploy_result: Optional[DeployResult] = None
    report_path: Optional[Path] = None
    status: str = "pending"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: Optional[str] = None
    error_message: Optional[str] = None


# ELI5: Like the whiteboard in the dispatch office showing every truck,
#       every delivery, and whether it's out, loading, or already back.
class OrchestratorState(BaseModel):
    """Live snapshot of the whole SimplePod fleet."""

    nodes: Dict[str, NodeDescriptor] = Field(default_factory=dict)
    active_payloads: Dict[str, LifecycleHandle] = Field(default_factory=dict)
    history: List[str] = Field(default_factory=list)


# =============================================================================
# Node Selection
# =============================================================================

# ELI5: Like the dispatcher looking at the map and picking the closest
#       electrician who isn't already stuck in someone else's attic.
def select_node(
    nodes: Dict[str, NodeDescriptor],
    require_capability: Optional[str] = None,
    strategy: str = "least_loaded",
) -> Optional[NodeDescriptor]:
    """Pick the best available node from the pool."""
    candidates = [n for n in nodes.values() if n.healthy]
    if require_capability:
        candidates = [
            n for n in candidates if require_capability in n.capabilities
        ]

    if not candidates:
        return None

    if strategy == "random":
        return random.choice(candidates)
    elif strategy == "least_loaded":
        return min(candidates, key=lambda n: n.current_tasks / n.max_tasks)
    elif strategy == "round_robin":
        return sorted(candidates, key=lambda n: n.node_id)[0]
    else:
        return candidates[0]


# =============================================================================
# Orchestration Stages
# =============================================================================

# ELI5: Like the warehouse manager who bundles up the breaker panel,
#       prints the address label, and hands the box to the shipping bay.
async def stage_payload(
    orchestrator: OrchestratorState,
    payload_id: str,
    node_id: str,
    tasks: List[TaskDefinition],
    artifacts: List[Path],
    payload_config: Optional[PayloadConfig] = None,
) -> LifecycleHandle:
    """Build a SITK payload targeted for a specific node."""
    handle = LifecycleHandle(payload_id=payload_id, node_id=node_id)
    node = orchestrator.nodes.get(node_id)
    if not node:
        handle.status = "failed"
        handle.error_message = f"Node {node_id} not found in dispatch board"
        return handle

    payload_path = await build_payload(
        payload_id=payload_id,
        source_node="orchestrator",
        target_node=node_id,
        tasks=tasks,
        artifacts=artifacts,
        config=payload_config,
    )
    handle.payload_path = payload_path
    handle.status = "staged"
    handle.updated_at = datetime.now(timezone.utc).isoformat()
    orchestrator.active_payloads[payload_id] = handle
    return handle


# ELI5: Like the shipping coordinator who radios the driver,
#       tells them which route to take, and watches the GPS tracker.
async def deploy_payload(
    orchestrator: OrchestratorState,
    handle: LifecycleHandle,
    remote_dir: str = "/tmp/simplepod_payloads",
    progress_callback: Optional[Callable[[TransferProgress], None]] = None,
) -> LifecycleHandle:
    """Deliver a staged payload to its assigned node."""
    node = orchestrator.nodes.get(handle.node_id)
    if not node or not handle.payload_path:
        handle.status = "failed"
        handle.error_message = "Missing node or payload path"
        return handle

    callbacks: List[Callable[[TransferProgress], None]] = []
    if progress_callback:
        callbacks.append(progress_callback)

    if node.is_local:
        result = await deploy_local(
            payload_path=handle.payload_path,
            target_dir=Path(remote_dir),
            progress_callbacks=callbacks,
        )
    else:
        creds = NodeCredentials(
            host=node.host,
            port=node.port,
            username=node.username,
            password=node.password,
            private_key_path=node.private_key_path,
        )
        # Extract expected digest from sidecar manifest if available.
        sidecar = handle.payload_path.with_suffix(".manifest.json")
        expected_sha256: Optional[str] = None
        if sidecar.exists():
            sidecar_data = json.loads(sidecar.read_text(encoding="utf-8"))
            expected_sha256 = sidecar_data.get("sha256_digest")

        result = await deploy_ssh(
            payload_path=handle.payload_path,
            credentials=creds,
            remote_dir=remote_dir,
            expected_sha256=expected_sha256,
            progress_callbacks=callbacks,
        )

    handle.deploy_result = result
    handle.status = "deployed" if result.success else "failed"
    if not result.success:
        handle.error_message = result.error_message or "Deployment failed"
    handle.updated_at = datetime.now(timezone.utc).isoformat()
    return handle


# ELI5: Like the foreman who walks into the job site, flips the main breaker,
#       watches the crew work, collects the inspection cards, and locks up.
async def execute_on_node(
    orchestrator: OrchestratorState,
    handle: LifecycleHandle,
    executor_config_overrides: Optional[Dict[str, Any]] = None,
) -> LifecycleHandle:
    """Run the executor on the target node and collect the report."""
    node = orchestrator.nodes.get(handle.node_id)
    if not node:
        handle.status = "failed"
        handle.error_message = "Node vanished from dispatch board"
        return handle

    if node.is_local:
        # Run executor directly in-process for local node.
        config = ExecutorConfig(
            payload_zip=handle.payload_path or Path("unknown.zip"),
            node_name=node.node_id,
            report_path=Path(f"./reports/{handle.payload_id}_report.json"),
        )
        if executor_config_overrides:
            for k, v in executor_config_overrides.items():
                if hasattr(config, k):
                    setattr(config, k, v)

        from .sitk_executor import execute as exec_runner

        report = await exec_runner(config)
        handle.report_path = config.report_path
        handle.status = "completed" if not report.error_message else "failed"
        if report.error_message:
            handle.error_message = report.error_message
    else:
        # Trigger remote execution via SSH command and retrieve report.
        handle.status = "executing"
        remote_zip = (
            f"/tmp/simplepod_payloads/{handle.payload_path.name}"
            if handle.payload_path
            else "unknown.zip"
        )
        remote_report = f"/tmp/simplepod_payloads/{handle.payload_id}_report.json"

        if not HAS_ASYNCSSH:
            handle.status = "failed"
            handle.error_message = "asyncssh required for remote execution orchestration"
            handle.updated_at = datetime.now(timezone.utc).isoformat()
            return handle

        try:
            conn_options: dict[str, Any] = {
                "host": node.host,
                "port": node.port,
                "username": node.username,
                "known_hosts": None,
            }
            if node.password:
                conn_options["password"] = node.password
            if node.private_key_path:
                conn_options["client_keys"] = [str(node.private_key_path)]

            async with asyncssh.connect(**conn_options) as conn:
                cmd = (
                    f"cd /tmp/simplepod_payloads && "
                    f"python -m simplepod_swarm.core.sitk.sitk_executor "
                    f"--zip {remote_zip} "
                    f"--report {remote_report} "
                    f"--node {node.node_id}"
                )
                result = await conn.run(cmd, check=False)

                # Fetch report back.
                try:
                    report_data = await conn.run(
                        f"cat {remote_report}", check=False
                    )
                    if report_data.stdout:
                        local_report = Path(
                            f"./reports/{handle.payload_id}_report.json"
                        )
                        local_report.parent.mkdir(parents=True, exist_ok=True)
                        local_report.write_text(
                            report_data.stdout, encoding="utf-8"
                        )
                        handle.report_path = local_report
                except Exception as exc:
                    handle.error_message = f"Report retrieval failed: {exc}"

                handle.status = (
                    "completed" if result.exit_status == 0 else "failed"
                )
                if result.exit_status != 0:
                    handle.error_message = (
                        result.stderr or "Remote execution failed"
                    )
        except Exception as exc:
            handle.status = "failed"
            handle.error_message = str(exc)

    handle.updated_at = datetime.now(timezone.utc).isoformat()
    return handle


# =============================================================================
# Full Lifecycle Convenience
# =============================================================================

# ELI5: Like the full-service home-automation company: you tell them
#       "install three smart switches and a new sub-panel," they pick
#       the right house, build the parts list, ship the truck, do the work,
#       send you the photos, and invoice you—all while you watch on an app.
async def run_full_lifecycle(
    orchestrator: OrchestratorState,
    payload_id: str,
    tasks: List[TaskDefinition],
    artifacts: Optional[List[Path]] = None,
    require_capability: Optional[str] = None,
    strategy: str = "least_loaded",
    remote_dir: str = "/tmp/simplepod_payloads",
    payload_config: Optional[PayloadConfig] = None,
    progress_callback: Optional[Callable[[TransferProgress], None]] = None,
) -> LifecycleHandle:
    """One-call convenience wrapper for the entire node lifecycle."""
    if artifacts is None:
        artifacts = []

    # Select node
    node = select_node(orchestrator.nodes, require_capability, strategy)
    if not node:
        handle = LifecycleHandle(payload_id=payload_id, node_id="none")
        handle.status = "failed"
        handle.error_message = "No suitable node found in fleet"
        orchestrator.active_payloads[payload_id] = handle
        return handle

    # Stage
    handle = await stage_payload(
        orchestrator,
        payload_id,
        node.node_id,
        tasks,
        artifacts,
        payload_config,
    )
    if handle.status == "failed":
        return handle

    # Deploy
    handle = await deploy_payload(
        orchestrator, handle, remote_dir, progress_callback
    )
    if handle.status == "failed":
        return handle

    # Execute
    handle = await execute_on_node(orchestrator, handle)

    orchestrator.history.append(
        f"{datetime.now(timezone.utc).isoformat()} | {payload_id} | {handle.status} | {node.node_id}"
    )
    return handle
