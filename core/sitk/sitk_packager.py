"""
Self-Installing Tool-Kit (SITK) Packager

Builds encrypted ZIP payloads with embedded manifests for remote execution.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

try:
    import pyzipper

    HAS_PYZIPPER = True
except ImportError:
    HAS_PYZIPPER = False


# =============================================================================
# Pydantic Models
# =============================================================================

# ELI5: Like an electrician's work-order form that lists every wire,
#       breaker, and outlet needed before showing up at the house.
class TaskDefinition(BaseModel):
    """Single unit of work to be executed on the remote node."""

    task_id: str = Field(..., description="Unique identifier for this task")
    command: str = Field(..., description="Shell command or script to run")
    working_dir: Optional[str] = Field(
        default=None, description="Where to run the command"
    )
    env_vars: Dict[str, str] = Field(
        default_factory=dict, description="Extra environment variables"
    )
    timeout_seconds: int = Field(
        default=300, ge=1, description="How long before the breaker trips"
    )
    gpu_required: bool = Field(
        default=False, description="Does this task need the GPU panel?"
    )


# ELI5: Like the packing slip taped to the outside of the electrical
#       panel box so the builder knows what's inside without opening it.
class PayloadManifest(BaseModel):
    """Inventory and metadata for a SITK payload."""

    manifest_version: str = Field(default="1.0.0")
    payload_id: str = Field(..., description="UUID for this payload shipment")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source_node: str = Field(..., description="Who built the panel")
    target_node: str = Field(..., description="Which house gets the panel")
    tasks: List[TaskDefinition] = Field(
        default_factory=list, description="Jobs to wire up"
    )
    artifacts: List[str] = Field(
        default_factory=list, description="Files bundled inside the box"
    )
    encryption_method: str = Field(
        default="aes256", description="Lock type on the toolbox"
    )
    sha256_digest: Optional[str] = Field(
        default=None, description="Fingerprint of the sealed box"
    )

    @field_validator("sha256_digest")
    @classmethod
    def _hash_looks_real(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if len(v) != 64:
            raise ValueError(
                "SHA-256 fingerprint must be exactly 64 hex characters, like a full serial number"
            )
        return v


# ELI5: Like choosing between a basic toolbox and a fireproof safe
#       when sending your expensive meters and probes across town.
class PayloadConfig(BaseModel):
    """Knobs and dials for how the ZIP is assembled."""

    output_dir: Path = Field(default=Path("./payloads"))
    password: Optional[str] = Field(default=None, description="Combination lock code")
    compression_level: int = Field(
        default=6, ge=1, le=9, description="How hard to squeeze the wires together"
    )
    encrypt: bool = Field(default=True, description="Put a padlock on the toolbox?")
    include_timestamp: bool = Field(
        default=True, description="Stamp the delivery ticket?"
    )


# =============================================================================
# Helpers
# =============================================================================

# ELI5: Like a quality-control inspector who weighs the sealed panel box
#       and writes down its exact weight so the truck driver can check later.
def _calculate_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file, one chunk at a time."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as fh:
        while chunk := fh.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()


# ELI5: Like the warehouse robot that gathers all the breakers, wires,
#       and blueprints, puts them in a locked toolbox, and prints a
#       shipping label with the manifest taped to the lid.
def _build_zip_sync(
    zip_path: Path,
    manifest: PayloadManifest,
    artifacts: List[Path],
    config: PayloadConfig,
) -> None:
    """Synchronous payload assembly so we can offload it to a thread."""
    if config.encrypt and HAS_PYZIPPER and config.password:
        # ELI5: Like a fireproof safe with a digital combination lock.
        with pyzipper.AESZipFile(
            zip_path,
            "w",
            compression=pyzipper.ZIP_DEFLATED,
            compresslevel=config.compression_level,
            encryption=pyzipper.WZ_AES,
        ) as zf:
            zf.setpassword(config.password.encode("utf-8"))
            manifest_bytes = manifest.model_dump_json(indent=2).encode("utf-8")
            zf.writestr("manifest.json", manifest_bytes)
            for art in artifacts:
                zf.write(art, arcname=art.name)
    else:
        # ELI5: Like a regular toolbox with a simple latch—keeps honest people honest.
        with zipfile.ZipFile(
            zip_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=config.compression_level,
        ) as zf:
            manifest_bytes = manifest.model_dump_json(indent=2).encode("utf-8")
            zf.writestr("manifest.json", manifest_bytes)
            for art in artifacts:
                zf.write(art, arcname=art.name)
            if config.encrypt and config.password:
                zf.comment = f"PASSWORD_HINT:{config.password}".encode("utf-8")


# =============================================================================
# Public API
# =============================================================================

# ELI5: Like the warehouse manager who bundles up the breaker panel,
#       prints the address label, and hands the box to the shipping bay.
async def build_payload(
    payload_id: str,
    source_node: str,
    target_node: str,
    tasks: List[TaskDefinition],
    artifacts: List[Path],
    config: Optional[PayloadConfig] = None,
) -> Path:
    """Assemble an encrypted SITK payload ZIP with embedded manifest."""
    config = config or PayloadConfig()
    config.output_dir.mkdir(parents=True, exist_ok=True)

    manifest = PayloadManifest(
        payload_id=payload_id,
        source_node=source_node,
        target_node=target_node,
        tasks=tasks,
        artifacts=[a.name for a in artifacts],
    )

    timestamp = (
        datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        if config.include_timestamp
        else ""
    )
    zip_name = f"sitk_{payload_id}{f'_{timestamp}' if timestamp else ''}.zip"
    zip_path = config.output_dir / zip_name

    # Offload blocking ZIP I/O to a worker thread.
    await asyncio.to_thread(_build_zip_sync, zip_path, manifest, artifacts, config)

    # Compute final digest in a thread so the event loop stays snappy.
    digest = await asyncio.to_thread(_calculate_sha256, zip_path)
    manifest.sha256_digest = digest

    # Write a sidecar manifest with the verified digest.
    sidecar_path = zip_path.with_suffix(".manifest.json")
    await asyncio.to_thread(
        sidecar_path.write_text,
        manifest.model_dump_json(indent=2),
        encoding="utf-8",
    )

    return zip_path
