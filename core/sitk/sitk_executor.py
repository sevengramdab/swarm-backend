"""
Self-Installing Tool-Kit (SITK) Executor

Runs on the target node: unpacks, primes GPU, runs tasks, collects telemetry, self-terminates.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

try:
    import torch

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


# =============================================================================
# Pydantic Models
# =============================================================================

# ELI5: Like the smart-meter readings an electrician takes before,
#       during, and after installing a new breaker panel.
class TelemetrySnapshot(BaseModel):
    """One slice of vital signs from the node while it works."""

    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    cpu_percent: Optional[float] = Field(default=None)
    memory_percent: Optional[float] = Field(default=None)
    memory_used_mb: Optional[float] = Field(default=None)
    gpu_name: Optional[str] = Field(default=None)
    gpu_utilization: Optional[float] = Field(default=None)
    gpu_memory_used_mb: Optional[float] = Field(default=None)
    gpu_temperature_c: Optional[float] = Field(default=None)


# ELI5: Like the sticker the inspector puts on each outlet saying
#       "passed," "failed," or "needs rewiring" with notes.
class TaskResult(BaseModel):
    """Outcome of one batched job."""

    task_id: str
    success: bool
    return_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    elapsed_seconds: float = 0.0
    telemetry_before: Optional[TelemetrySnapshot] = None
    telemetry_after: Optional[TelemetrySnapshot] = None


# ELI5: Like the final inspection report the city receives after
#       the whole house has been rewired and the crew has gone home.
class ExecutionReport(BaseModel):
    """Complete dossier from an executor run."""

    payload_id: str
    node_name: str
    started_at: str
    finished_at: Optional[str] = None
    tasks: List[TaskResult] = Field(default_factory=list)
    telemetry_series: List[TelemetrySnapshot] = Field(default_factory=list)
    self_terminated: bool = False
    error_message: Optional[str] = None


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class ExecutorConfig:
    """Switches on the executor's control board."""

    payload_zip: Path
    extract_dir: Optional[Path] = None
    password: Optional[str] = None
    prime_gpu: bool = True
    cleanup_after: bool = True
    node_name: str = "unknown-node"
    report_path: Optional[Path] = None


# =============================================================================
# Telemetry & GPU Priming
# =============================================================================

# ELI5: Like the apprentice who walks around with a clipboard checking
#       how hot the transformer is and how much load is on each circuit.
def _collect_telemetry() -> TelemetrySnapshot:
    """Gather a single snapshot of node health."""
    snap = TelemetrySnapshot()

    if HAS_PSUTIL:
        snap.cpu_percent = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        snap.memory_percent = mem.percent
        snap.memory_used_mb = mem.used / (1024 * 1024)

    if HAS_TORCH and torch.cuda.is_available():
        snap.gpu_name = torch.cuda.get_device_name(0)
        snap.gpu_memory_used_mb = torch.cuda.memory_allocated(0) / (1024 * 1024)
        # Try nvidia-smi for utilization & temperature.
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(", ")
                if len(parts) == 2:
                    snap.gpu_utilization = float(parts[0])
                    snap.gpu_temperature_c = float(parts[1])
        except Exception:
            pass

    return snap


# ELI5: Like flipping every breaker on and off once before the real work
#       starts, just to make sure the panel doesn't spark when the load hits.
def _prime_gpu() -> None:
    """Warm up the CUDA context so later tasks don't pay init overhead."""
    if not HAS_TORCH:
        return
    if not torch.cuda.is_available():
        return

    # ELI5: Like turning on every light in the house for two seconds
    #       to warm up the circuits before the real party begins.
    device = torch.device("cuda:0")
    dummy = torch.randn(1024, 1024, device=device)
    _ = torch.matmul(dummy, dummy)
    torch.cuda.synchronize()


# =============================================================================
# Payload Unpacking
# =============================================================================

# ELI5: Like the contractor who cuts the seal on the delivery box,
#       pulls out the blueprints, and spreads tools across the workbench.
def _unpack_payload_sync(config: ExecutorConfig) -> Path:
    """Extract ZIP to a temp folder and return the folder path."""
    extract_to = config.extract_dir or Path(tempfile.mkdtemp(prefix="sitk_"))
    extract_to.mkdir(parents=True, exist_ok=True)

    if config.password:
        try:
            import pyzipper

            with pyzipper.AESZipFile(
                config.payload_zip, "r", encryption=pyzipper.WZ_AES
            ) as zf:
                zf.setpassword(config.password.encode("utf-8"))
                zf.extractall(path=str(extract_to))
            return extract_to
        except Exception:
            pass

    with zipfile.ZipFile(config.payload_zip, "r") as zf:
        zf.extractall(path=str(extract_to))
    return extract_to


# =============================================================================
# Task Execution
# =============================================================================

# ELI5: Like the journeyman electrician who reads the work order,
#       wires one outlet at a time, and marks each one done on the clipboard.
async def _run_task(task_def: Dict[str, Any], work_dir: Path) -> TaskResult:
    """Execute a single task definition with telemetry bookends."""
    task_id = task_def.get("task_id", "unknown")
    result = TaskResult(task_id=task_id)

    # Pre-job vitals
    result.telemetry_before = await asyncio.to_thread(_collect_telemetry)

    cmd = task_def.get("command", "")
    cwd = task_def.get("working_dir")
    if cwd:
        cwd = str(work_dir / cwd)
    else:
        cwd = str(work_dir)

    env = os.environ.copy()
    env.update(task_def.get("env_vars", {}))
    timeout = task_def.get("timeout_seconds", 300)

    start = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        result.return_code = proc.returncode
        result.stdout = stdout_bytes.decode("utf-8", errors="replace")
        result.stderr = stderr_bytes.decode("utf-8", errors="replace")
        result.success = proc.returncode == 0
    except asyncio.TimeoutError:
        result.success = False
        result.stderr = f"Task exceeded timeout of {timeout} seconds"
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
    except Exception as exc:
        result.success = False
        result.stderr = str(exc)

    result.elapsed_seconds = time.monotonic() - start

    # Post-job vitals
    result.telemetry_after = await asyncio.to_thread(_collect_telemetry)

    return result


# =============================================================================
# Main Lifecycle
# =============================================================================

# ELI5: Like the general contractor who opens the toolbox at dawn,
#       checks that the generator starts, runs every job on the punch list,
#       writes the inspection report, locks the door, and throws away the key.
async def execute(config: ExecutorConfig) -> ExecutionReport:
    """Full lifecycle: unpack, prime, run, report, cleanup, self-terminate."""
    payload_id = config.payload_zip.stem
    report = ExecutionReport(
        payload_id=payload_id,
        node_name=config.node_name,
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    extract_dir: Optional[Path] = None
    try:
        # Unpack
        extract_dir = await asyncio.to_thread(_unpack_payload_sync, config)

        # Load manifest
        manifest_path = extract_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        # Prime GPU
        if config.prime_gpu:
            await asyncio.to_thread(_prime_gpu)

        # Run tasks
        for task_def in manifest.get("tasks", []):
            task_result = await _run_task(task_def, extract_dir)
            report.tasks.append(task_result)
            # Collect mid-run telemetry
            report.telemetry_series.append(await asyncio.to_thread(_collect_telemetry))

    except Exception as exc:
        report.error_message = str(exc)
    finally:
        # Cleanup
        if config.cleanup_after and extract_dir and extract_dir.exists():
            await asyncio.to_thread(shutil.rmtree, str(extract_dir), ignore_errors=True)

        report.finished_at = datetime.now(timezone.utc).isoformat()

        # Write report
        if config.report_path:
            config.report_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(
                config.report_path.write_text,
                report.model_dump_json(indent=2),
                encoding="utf-8",
            )

        # Self-terminate flag
        report.self_terminated = True
        if config.report_path:
            await asyncio.to_thread(
                config.report_path.write_text,
                report.model_dump_json(indent=2),
                encoding="utf-8",
            )

    return report


# ELI5: Like the kill-switch on a power tool that shuts everything down
#       instantly if someone's finger slips or a wire starts smoking.
def self_terminate(exit_code: int = 0) -> None:
    """Immediately end the executor process."""
    sys.exit(exit_code)


# =============================================================================
# CLI Entrypoint
# =============================================================================

# ELI5: Like the doorbell panel outside the house: a visitor punches in
#       a few numbers, and the system knows exactly which unit to buzz.
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SITK Executor Node Agent")
    parser.add_argument("--zip", required=True, type=Path, help="Payload archive")
    parser.add_argument("--report", type=Path, default=None, help="Where to write JSON report")
    parser.add_argument("--node", type=str, default="unknown-node", help="Name of this node")
    parser.add_argument("--password", type=str, default=None, help="ZIP password")
    parser.add_argument("--no-prime-gpu", action="store_true", help="Skip GPU warmup")
    parser.add_argument("--no-cleanup", action="store_true", help="Leave extracted files")
    args = parser.parse_args()

    cfg = ExecutorConfig(
        payload_zip=args.zip,
        report_path=args.report,
        node_name=args.node,
        password=args.password,
        prime_gpu=not args.no_prime_gpu,
        cleanup_after=not args.no_cleanup,
    )

    report = asyncio.run(execute(cfg))
    self_terminate(0 if not report.error_message else 1)
