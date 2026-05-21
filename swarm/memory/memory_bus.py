#!/usr/bin/env python3
"""
memory_bus.py
=============
The central Memory Bus — like the Layer Properties Manager in AutoCAD.

ELI5 Analogy:
  Imagine every agent is drawing on a different layer in Model Space.
  When a drawing station (node) crashes, you don't lose the layer because
  the Layer Properties Manager (Memory Bus) saves every layer's color,
  linetype, and visibility to the master template file (JSONL log).
  When a new station boots up, it loads the template and all layers
  reappear exactly as they were.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Pydantic models for structured memory records
# ---------------------------------------------------------------------------

class MemoryRecord(BaseModel):
    """A single entry on the memory bus — like one row in the Layer Properties palette."""

    record_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    topic: str  # e.g. "agent_registry", "task_state", "routing_config"
    payload: Dict[str, Any]
    timestamp: float = Field(default_factory=time.time)
    node_id: Optional[str] = None
    agent_id: Optional[str] = None
    ttl: Optional[float] = None  # seconds until auto-expire


class MemoryBus:
    """
    Singleton memory bus with async read/write and append-only JSONL persistence.

    Think of this as the main electrical panel's data logger:
    every circuit (agent) reports its voltage and current (state)
    to a central logbook (JSONL file) that survives power outages
    because it's written to disk immediately.
    """

    _instance: Optional[MemoryBus] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):  # noqa: ARG004
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        persist_path: Optional[Path] = None,
        max_in_memory: int = 10_000,
    ) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        # ELI5: The logbook file where we write every layer change.
        #       If no path given, we use a local notebook (memory_only=False).
        self.persist_path: Optional[Path] = persist_path or Path("swarm_memory.jsonl")
        self.max_in_memory = max_in_memory

        # In-memory ring buffer — like the recent-items tray on a drafter's desk.
        self._records: List[MemoryRecord] = []
        self._index: Dict[str, List[MemoryRecord]] = {}  # topic -> records
        self._write_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def write(self, record: MemoryRecord) -> str:
        """
        ELI5: Like clicking the SAVE button on a layer change in AutoCAD.
              The change goes into the drawing's memory (RAM) AND gets
              written to the .dwg file on disk so it survives a crash.
        """
        async with self._write_lock:
            self._records.append(record)
            self._index.setdefault(record.topic, []).append(record)

            # Trim old records if desk tray is overflowing.
            if len(self._records) > self.max_in_memory:
                evicted = self._records.pop(0)
                self._index[evicted.topic].remove(evicted)

            # Persist to JSONL immediately — the "save to disk" step.
            if self.persist_path:
                await self._append_to_disk(record)

        return record.record_id

    async def read(
        self,
        topic: str,
        since: Optional[float] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[MemoryRecord]:
        """
        ELI5: Like opening the Layer Properties Manager and filtering
              to show only the "ELECTRICAL" layers, or only layers
              modified after 2 PM (since), or only layers drawn by
              Engineer #7 (agent_id).
        """
        async with self._write_lock:
            candidates = self._index.get(topic, [])
            results: List[MemoryRecord] = []
            for rec in reversed(candidates):
                if since and rec.timestamp < since:
                    continue
                if agent_id and rec.agent_id != agent_id:
                    continue
                if rec.ttl and (time.time() - rec.timestamp) > rec.ttl:
                    continue
                results.append(rec)
                if len(results) >= limit:
                    break
            return list(reversed(results))

    async def get_latest(self, topic: str, agent_id: Optional[str] = None) -> Optional[MemoryRecord]:
        """Return the most recent record for a topic — like the last-saved layer state."""
        results = await self.read(topic, agent_id=agent_id, limit=1)
        return results[0] if results else None

    async def replay(
        self,
        topics: Optional[List[str]] = None,
        since: Optional[float] = None,
    ) -> List[MemoryRecord]:
        """
        ELI5: Like using the UNDO/REDO history palette in AutoCAD.
              You can scroll back to any point in time and replay
              every command that changed the drawing.
        """
        async with self._write_lock:
            records = self._records
            if topics:
                records = [r for r in records if r.topic in topics]
            if since:
                records = [r for r in records if r.timestamp >= since]
            return sorted(records, key=lambda r: r.timestamp)

    async def prune_expired(self) -> int:
        """
        ELI5: Like purging unused layers (LAYDEL) to keep the drawing
              file from bloating. If a layer hasn't been used in 30 days,
              it's just electrical noise — delete it.
        """
        now = time.time()
        removed = 0
        async with self._write_lock:
            survivors: List[MemoryRecord] = []
            for rec in self._records:
                if rec.ttl and (now - rec.timestamp) > rec.ttl:
                    removed += 1
                    continue
                survivors.append(rec)
            self._records = survivors

            # Rebuild index
            self._index = {}
            for rec in self._records:
                self._index.setdefault(rec.topic, []).append(rec)
        return removed

    async def recover_from_disk(self) -> int:
        """
        ELI5: Like recovering a .bak file after AutoCAD crashes.
              We read every line in the logbook and rebuild the
              Layer Properties Manager from scratch.
        """
        if not self.persist_path or not self.persist_path.exists():
            return 0

        count = 0
        async with self._write_lock:
            async with aiofiles.open(self.persist_path, "r", encoding="utf-8") as f:
                async for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        record = MemoryRecord(**data)
                        self._records.append(record)
                        self._index.setdefault(record.topic, []).append(record)
                        count += 1
                    except Exception:
                        continue  # corrupted line — like a smudged logbook entry

            # Enforce memory ceiling after recovery
            overflow = len(self._records) - self.max_in_memory
            if overflow > 0:
                evicted = self._records[:overflow]
                self._records = self._records[overflow:]
                for rec in evicted:
                    self._index[rec.topic].remove(rec)

        return count

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _append_to_disk(self, record: MemoryRecord) -> None:
        """Append a single record as a JSON line — like writing one entry in a logbook."""
        if not self.persist_path:
            return
        # Ensure parent directory exists (the file cabinet drawer).
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        line = record.model_dump_json() + "\n"
        async with aiofiles.open(self.persist_path, "a", encoding="utf-8") as f:
            await f.write(line)

    async def close(self) -> None:
        """Graceful shutdown — close the logbook and lock the drawer."""
        # Nothing explicit needed for JSONL, but reserved for future flush logic.
        pass
