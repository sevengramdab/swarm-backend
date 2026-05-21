"""
Self-Installing Tool-Kit (SITK) Deployer

Delivers payload archives to target nodes over SSH/SCP or local filesystem.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from pydantic import BaseModel, Field

try:
    import asyncssh

    HAS_ASYNCSSH = True
except ImportError:
    HAS_ASYNCSSH = False

try:
    import paramiko

    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False


# =============================================================================
# Pydantic Models
# =============================================================================

# ELI5: Like the delivery ticket that says which truck, which route,
#       and whether the driver needs a gate code to enter the neighborhood.
class NodeCredentials(BaseModel):
    """Authentication and addressing info for a target node."""

    host: str = Field(..., description="Street address of the house")
    port: int = Field(default=22, description="Which driveway entrance to use")
    username: str = Field(..., description="Name on the mailbox")
    password: Optional[str] = Field(default=None, description="Gate code")
    private_key_path: Optional[Path] = Field(
        default=None, description="Electronic key-fob file"
    )
    known_hosts_path: Optional[Path] = Field(
        default=None, description="Trusted-neighborhood list"
    )


# ELI5: Like a GPS tracker that pings every minute so you know if the truck
#       is stuck at a red light or already backing into the driveway.
class TransferProgress(BaseModel):
    """Snapshot of how the delivery is going."""

    bytes_transferred: int = Field(default=0)
    bytes_total: int = Field(default=0)
    percent: float = Field(default=0.0)
    current_file: str = Field(default="")
    status: str = Field(default="idle")  # idle, transferring, verifying, done, error


# ELI5: Like the final signed receipt the homeowner gives the driver
#       after inspecting the package for dents and checking the serial number.
class DeployResult(BaseModel):
    """Outcome of a deployment attempt."""

    success: bool
    payload_path: Path
    target_node: str
    remote_path: Optional[str] = None
    sha256_matched: bool = False
    error_message: Optional[str] = None
    elapsed_seconds: float = 0.0


# =============================================================================
# Internal State
# =============================================================================

@dataclass
class _DeployerState:
    """Mutable state tracked during an active delivery run."""

    progress: TransferProgress = field(default_factory=TransferProgress)
    callbacks: List[Callable[[TransferProgress], None]] = field(default_factory=list)


# =============================================================================
# Helpers
# =============================================================================

# ELI5: Like calling the homeowner on a walkie-talkie to say,
#       "The truck is 50 feet from your mailbox—get ready to open the garage."
def _notify(state: _DeployerState) -> None:
    """Fire all progress callbacks so upstream dashboards stay fresh."""
    for cb in state.callbacks:
        try:
            cb(state.progress)
        except Exception:
            pass


# ELI5: Like a truck driver who checks the bill of lading against
#       the stamp on the crate before lifting it off the flatbed.
def _verify_file_hash(file_path: Path, expected_digest: str) -> bool:
    """Compare local SHA-256 to the manifest digest."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as fh:
        while chunk := fh.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower() == expected_digest.lower()


# =============================================================================
# Deployment Engines
# =============================================================================

# ELI5: Like a local courier who just drives the package across town
#       in their own van and drops it on the front porch—no shipping company needed.
async def deploy_local(
    payload_path: Path,
    target_dir: Path,
    expected_sha256: Optional[str] = None,
    progress_callbacks: Optional[List[Callable[[TransferProgress], None]]] = None,
) -> DeployResult:
    """Copy payload to a local directory with optional hash verification."""
    import time

    start = time.monotonic()
    state = _DeployerState()
    if progress_callbacks:
        state.callbacks.extend(progress_callbacks)

    state.progress.current_file = payload_path.name
    state.progress.bytes_total = payload_path.stat().st_size
    state.progress.status = "transferring"
    _notify(state)

    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / payload_path.name

    # ELI5: Like carrying boxes one at a time instead of trying to lift the whole shed.
    bytes_done = 0
    chunk_size = 65536
    with open(payload_path, "rb") as src, open(dest, "wb") as dst:
        while True:
            chunk = src.read(chunk_size)
            if not chunk:
                break
            dst.write(chunk)
            bytes_done += len(chunk)
            state.progress.bytes_transferred = bytes_done
            if state.progress.bytes_total > 0:
                state.progress.percent = round(
                    (bytes_done / state.progress.bytes_total) * 100, 2
                )
            _notify(state)

    state.progress.status = "verifying"
    _notify(state)

    matched = True
    if expected_sha256:
        matched = await asyncio.to_thread(_verify_file_hash, dest, expected_sha256)

    state.progress.status = "done" if matched else "error"
    _notify(state)

    elapsed = time.monotonic() - start
    return DeployResult(
        success=matched,
        payload_path=payload_path,
        target_node="localhost",
        remote_path=str(dest),
        sha256_matched=matched,
        elapsed_seconds=elapsed,
        error_message=None if matched else "SHA-256 mismatch after local copy",
    )


# ELI5: Like a long-haul trucking company that uses satellite radios
#       to send your locked toolbox to a house three states away.
async def deploy_ssh(
    payload_path: Path,
    credentials: NodeCredentials,
    remote_dir: str,
    expected_sha256: Optional[str] = None,
    progress_callbacks: Optional[List[Callable[[TransferProgress], None]]] = None,
) -> DeployResult:
    """SCP-style delivery over SSH with async progress pings."""
    import time

    start = time.monotonic()
    state = _DeployerState()
    if progress_callbacks:
        state.callbacks.extend(progress_callbacks)

    state.progress.current_file = payload_path.name
    state.progress.bytes_total = payload_path.stat().st_size
    state.progress.status = "transferring"
    _notify(state)

    remote_path = f"{remote_dir}/{payload_path.name}"
    matched = False
    error_msg: Optional[str] = None

    # Prefer asyncssh for native async I/O.
    if HAS_ASYNCSSH:
        try:
            conn_options: dict[str, Any] = {
                "host": credentials.host,
                "port": credentials.port,
                "username": credentials.username,
                "known_hosts": None,  # In production, set properly.
            }
            if credentials.password:
                conn_options["password"] = credentials.password
            if credentials.private_key_path:
                conn_options["client_keys"] = [str(credentials.private_key_path)]

            async with asyncssh.connect(**conn_options) as conn:
                # Ensure remote landing zone exists.
                await conn.run(f"mkdir -p {remote_dir}", check=True)

                # ELI5: Like the truck's lift-gate slowly lowering the crate
                #       while the dispatcher watches the weight sensor.
                async def _progress_handler(
                    src: str, dst: str, size: int, bytes_sent: int
                ) -> None:
                    state.progress.bytes_transferred = bytes_sent
                    state.progress.bytes_total = size
                    if size > 0:
                        state.progress.percent = round(
                            (bytes_sent / size) * 100, 2
                        )
                    _notify(state)

                await asyncssh.scp(
                    str(payload_path),
                    (conn, remote_path),
                    progress_handler=_progress_handler,
                )

                # Verify integrity on the far side.
                state.progress.status = "verifying"
                _notify(state)
                if expected_sha256:
                    result = await conn.run(
                        f"sha256sum {remote_path} | awk '{{print $1}}'",
                        check=True,
                    )
                    remote_hash = result.stdout.strip()
                    matched = remote_hash.lower() == expected_sha256.lower()
                else:
                    matched = True
        except Exception as exc:
            error_msg = str(exc)
            matched = False

    elif HAS_PARAMIKO:
        # Fallback: paramiko inside a thread so we don't block the loop.
        def _paramiko_copy() -> bool:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            connect_kwargs: dict[str, Any] = {
                "hostname": credentials.host,
                "port": credentials.port,
                "username": credentials.username,
            }
            if credentials.password:
                connect_kwargs["password"] = credentials.password
            if credentials.private_key_path:
                connect_kwargs["key_filename"] = str(credentials.private_key_path)
            client.connect(**connect_kwargs)

            sftp = client.open_sftp()
            try:
                try:
                    sftp.mkdir(remote_dir)
                except IOError:
                    pass  # Directory already exists.

                def _callback(bytes_sent: int, bytes_total: int) -> None:
                    state.progress.bytes_transferred = bytes_sent
                    state.progress.bytes_total = bytes_total
                    if bytes_total > 0:
                        state.progress.percent = round(
                            (bytes_sent / bytes_total) * 100, 2
                        )
                    _notify(state)

                sftp.put(str(payload_path), remote_path, callback=_callback)

                if expected_sha256:
                    stdin, stdout, stderr = client.exec_command(
                        f"sha256sum {remote_path} | awk '{{print $1}}'"
                    )
                    remote_hash = stdout.read().decode().strip()
                    return remote_hash.lower() == expected_sha256.lower()
                return True
            finally:
                sftp.close()
                client.close()

        try:
            matched = await asyncio.to_thread(_paramiko_copy)
        except Exception as exc:
            error_msg = str(exc)
            matched = False
    else:
        error_msg = "No SSH library installed (asyncssh or paramiko required)"
        matched = False

    elapsed = time.monotonic() - start
    state.progress.status = "done" if matched else "error"
    _notify(state)

    return DeployResult(
        success=matched,
        payload_path=payload_path,
        target_node=credentials.host,
        remote_path=remote_path,
        sha256_matched=matched,
        elapsed_seconds=elapsed,
        error_message=error_msg,
    )
