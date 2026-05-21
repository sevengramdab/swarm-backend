"""
Telemetry Logger — Async batched JSONL logger with rotation and compression.

ELI5: Imagine a conveyor belt in a factory drawing. Instead of one worker running
to the filing cabinet after every single part, we collect parts in a little bin.
When the bin gets full (or the timer dings), a robot whisksthe bin to the cabinet,
zips it into a tiny compressed envelope, and swaps in a fresh bin. That is exactly
what this logger does with telemetry events.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import aiofiles
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Pydantic models — like title blocks on an engineering drawing
# ---------------------------------------------------------------------------

class TelemetryEvent(BaseModel):
    """
    ELI5: Think of this as a dimension line on a blueprint. It tells you
    *what* happened, *when* it happened, and *where* on the drawing to look.
    """
    event_id: str = Field(..., description="Unique identifier, like a part number.")
    timestamp: float = Field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    source: str = Field(..., description="Which machine or agent sent the event.")
    event_type: str = Field(..., description="Category: 'metric', 'log', 'span', etc.")
    payload: dict[str, Any] = Field(default_factory=dict, description="The actual measurement data.")
    tags: dict[str, str] = Field(default_factory=dict, description="Labels, like material callouts.")

    @field_validator("event_id")
    @classmethod
    def _event_id_not_empty(cls, v: str) -> str:
        # ELI5: A part number can't be blank — same rule here.
        if not v.strip():
            raise ValueError("event_id must not be empty (no blank title blocks allowed).")
        return v


class LoggerConfig(BaseModel):
    """
    ELI5: This is the drawing's general-notes section. It sets the scale,
    paper size, and how many sheets fit in the binder before you start a new one.
    """
    base_dir: Path = Field(default=Path("./telemetry_logs"))
    batch_size: int = Field(default=100, ge=1, description="How many events fit in the bin.")
    flush_interval_sec: float = Field(default=5.0, ge=0.1, description="Maximum seconds before the robot runs.")
    max_file_size_bytes: int = Field(default=10_485_760, ge=1, description="10 MB default — size of one drawing sheet.")
    max_backup_files: int = Field(default=5, ge=1, description="How many old rolled sheets to keep.")
    compress_on_rotate: bool = Field(default=True, description="Zip old sheets into envelopes?")
    file_prefix: str = Field(default="telemetry")


# ---------------------------------------------------------------------------
# Rotation helper — like swapping drawing sheets on a drafting table
# ---------------------------------------------------------------------------

@dataclass
class _RotationState:
    """
    ELI5: The clamp that holds the current sheet of paper. When the sheet
    gets too full of ink, we swap it for a fresh one.
    """
    current_path: Path
    current_size: int = 0
    sequence: int = 0


class TelemetryLogger:
    """
    ELI5: This is the entire drafting station.
    - A stack of dimension lines (events) sits on the desk.
    - Every few seconds (or when the stack gets tall), a robot grabs the stack,
      writes it neatly onto the current drawing sheet, and files it away.
    - When a sheet is full, it gets rolled up, zipped into a storage tube,
      and a fresh sheet is clipped to the board.
    """

    def __init__(self, config: LoggerConfig | None = None) -> None:
        # ELI5: Unroll the general notes and set up the drafting table.
        self._cfg: LoggerConfig = config or LoggerConfig()
        self._buffer: deque[TelemetryEvent] = deque()
        self._lock: asyncio.Lock = asyncio.Lock()
        self._flush_task: asyncio.Task[Any] | None = None
        self._closed: bool = False
        self._state: _RotationState | None = None
        self._hooks: list[Callable[[TelemetryEvent], Any]] = []

    # ------------------------------------------------------------------
    # Lifecycle — open and close the drafting station
    # ------------------------------------------------------------------

    async def open(self) -> None:
        """
        ELI5: Flip on the desk lamp and clip the first blank sheet to the board.
        """
        if self._state is not None:
            return
        self._cfg.base_dir.mkdir(parents=True, exist_ok=True)
        self._state = await self._init_new_sheet()
        self._flush_task = asyncio.create_task(self._timed_flush_loop())

    async def close(self) -> None:
        """
        ELI5: The whistle blew — finish writing, roll up the last sheet,
        put everything in storage, and turn off the lamp.
        """
        self._closed = True
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass  # ELI5: The robot stopped when the power went off. That's expected.
        async with self._lock:
            await self._flush_buffer()

    async def __aenter__(self) -> "TelemetryLogger":
        await self.open()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Public API — drop dimension lines on the desk
    # ------------------------------------------------------------------

    async def log(self, event: TelemetryEvent) -> None:
        """
        ELI5: A machinist walks up and lays a new measurement on the desk.
        We put it in the stack. If the stack is now taller than the bin limit,
        we tell the robot to run immediately.
        """
        if self._closed:
            raise RuntimeError("Logger is closed — the drafting station is locked.")
        async with self._lock:
            self._buffer.append(event)
            for hook in self._hooks:
                try:
                    hook(event)
                except Exception:
                    pass  # ELI5: A sticky note reminder fell on the floor; ignore it.
            if len(self._buffer) >= self._cfg.batch_size:
                await self._flush_buffer()

    async def log_many(self, events: list[TelemetryEvent]) -> None:
        """
        ELI5: A whole cart of measurements arrives at once. We unload them
        into the bin together so the robot only has to make one trip.
        """
        if self._closed:
            raise RuntimeError("Logger is closed — the drafting station is locked.")
        async with self._lock:
            self._buffer.extend(events)
            for ev in events:
                for hook in self._hooks:
                    try:
                        hook(ev)
                    except Exception:
                        pass
            if len(self._buffer) >= self._cfg.batch_size:
                await self._flush_buffer()

    def add_hook(self, hook: Callable[[TelemetryEvent], Any]) -> None:
        """
        ELI5: Stick a little bell on the desk that rings every time a new
        measurement lands. Other workers can listen for the bell.
        """
        self._hooks.append(hook)

    # ------------------------------------------------------------------
    # Internal machinery — the robot and the sheet swapper
    # ------------------------------------------------------------------

    async def _timed_flush_loop(self) -> None:
        """
        ELI5: A kitchen timer sits on the desk. Every few seconds it dings,
        and the robot checks whether there are any loose measurements to file.
        """
        while not self._closed:
            try:
                await asyncio.sleep(self._cfg.flush_interval_sec)
            except asyncio.CancelledError:
                break
            async with self._lock:
                if self._buffer:
                    await self._flush_buffer()

    async def _flush_buffer(self) -> None:
        """
        ELI5: The robot grabs every measurement in the bin, writes each one
        as a single line on the current drawing sheet (JSONL = one line per event),
        and then clears the bin for the next batch.
        """
        if not self._buffer or self._state is None:
            return

        lines: list[str] = []
        while self._buffer:
            ev = self._buffer.popleft()
            lines.append(ev.model_dump_json())
        block = "\n".join(lines) + "\n"
        block_bytes = block.encode("utf-8")

        await self._ensure_sheet_capacity(len(block_bytes))
        async with aiofiles.open(self._state.current_path, "ab") as f:
            await f.write(block_bytes)
        self._state.current_size += len(block_bytes)

    async def _ensure_sheet_capacity(self, needed: int) -> None:
        """
        ELI5: Before writing, check whether the current drawing sheet has
        enough blank space left. If not, roll it up and clip a fresh one.
        """
        if self._state is None:
            raise RuntimeError("Logger not opened — no sheet clipped to the board.")
        if self._state.current_size + needed > self._cfg.max_file_size_bytes:
            await self._rotate_sheet()

    async def _rotate_sheet(self) -> None:
        """
        ELI5: The sheet is full! Roll it up, zip it into a storage tube,
        and clip a brand-new blank sheet to the drafting board.
        """
        if self._state is None:
            return
        old_path = self._state.current_path
        if self._cfg.compress_on_rotate and old_path.exists():
            await self._compress_and_archive(old_path)
        self._state = await self._init_new_sheet()

    async def _compress_and_archive(self, path: Path) -> None:
        """
        ELI5: Take the rolled-up drawing sheet, slide it into a vacuum-seal
        bag (gzip), and store it in the archive cabinet. If the cabinet is
        too full, recycle the oldest tube.
        """
        gz_path = path.with_suffix(".jsonl.gz")
        async with aiofiles.open(path, "rb") as src:
            data = await src.read()
        compressed = gzip.compress(data, compresslevel=6)
        async with aiofiles.open(gz_path, "wb") as dst:
            await dst.write(compressed)
        path.unlink(missing_ok=True)
        await self._trim_archive()

    async def _trim_archive(self) -> None:
        """
        ELI5: The archive cabinet only has so many shelves. If we have more
        old tubes than shelves, toss the dustiest one.
        """
        pattern = f"{self._cfg.file_prefix}_*.jsonl.gz"
        backups = sorted(
            self._cfg.base_dir.glob(pattern),
            key=lambda p: p.stat().st_mtime,
        )
        excess = len(backups) - self._cfg.max_backup_files
        if excess > 0:
            for old in backups[:excess]:
                old.unlink(missing_ok=True)

    async def _init_new_sheet(self) -> _RotationState:
        """
        ELI5: Grab a fresh sheet of vellum, stamp it with today's date and
        a sequence number, and clip it to the board.
        """
        seq = int(time.time() * 1000)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{self._cfg.file_prefix}_{ts}_{seq}.jsonl"
        path = self._cfg.base_dir / filename
        async with aiofiles.open(path, "w") as f:
            await f.write("")
        return _RotationState(current_path=path, current_size=0, sequence=seq)

    # ------------------------------------------------------------------
    # Introspection — how tall is the stack?
    # ------------------------------------------------------------------

    @property
    def pending_count(self) -> int:
        """
        ELI5: How many measurements are still sitting in the bin, waiting
        for the robot to file them?
        """
        return len(self._buffer)

    def current_file_path(self) -> Path | None:
        """
        ELI5: Which drawing sheet is currently clipped to the board?
        """
        return self._state.current_path if self._state else None
