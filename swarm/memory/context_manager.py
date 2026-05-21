#!/usr/bin/env python3
"""
context_manager.py
==================
Stateful context lifecycle manager.

ELI5 Analogy:
  In AutoCAD, you work in Model Space but you can save named views
  (Viewports) to jump back to later. ContextManager is like the
  Viewport Manager — it saves snapshots of your entire workspace
  so you can restore them, branch them (make copies to explore
  alternatives), and prune old ones when your hard drive gets full.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
from pydantic import BaseModel, Field


class Checkpoint(BaseModel):
    """A saved viewport snapshot — a frozen moment in the drawing's history."""

    checkpoint_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    session_id: str
    label: str
    state_blob: Dict[str, Any]
    created_at: float = Field(default_factory=time.time)
    parent_checkpoint: Optional[str] = None  # for branching history


class ContextSession(BaseModel):
    """
    A logical drawing session that can span multiple workstations.

    ELI5: Like a .dwg file that stays open even when you move from
          your desk computer to the plotter room laptop. The file
          carries every layer, block, and dimension with it.
    """

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    name: str = "unnamed_session"
    created_at: float = Field(default_factory=time.time)
    last_active: float = Field(default_factory=time.time)
    checkpoints: List[Checkpoint] = Field(default_factory=list)
    current_state: Dict[str, Any] = Field(default_factory=dict)
    branch_depth: int = 0
    max_checkpoints: int = 50

    def touch(self) -> None:
        """Mark the session as recently used — like saving the drawing."""
        self.last_active = time.time()

    def add_checkpoint(self, label: str, state: Dict[str, Any], parent: Optional[str] = None) -> Checkpoint:
        """
        ELI5: Click SAVE VIEWPORT in AutoCAD. You give it a name
              (label) and it stores the current zoom, layers, and
              UCS orientation (state). You can have 50 of these
              before old ones get deleted to save disk space.
        """
        if len(self.checkpoints) >= self.max_checkpoints:
            # Prune oldest checkpoint — like deleting old backup .bak files.
            self.checkpoints.pop(0)

        cp = Checkpoint(
            session_id=self.session_id,
            label=label,
            state_blob=state.copy(),
            parent_checkpoint=parent,
        )
        self.checkpoints.append(cp)
        self.current_state = state.copy()
        self.touch()
        return cp

    def restore_checkpoint(self, checkpoint_id: str) -> bool:
        """
        ELI5: Double-click a saved Viewport name — boom, you're back
              to that exact zoom, pan, and layer freeze/thaw state.
        """
        for cp in self.checkpoints:
            if cp.checkpoint_id == checkpoint_id:
                self.current_state = cp.state_blob.copy()
                self.touch()
                return True
        return False

    def branch(self, new_name: str) -> ContextSession:
        """
        ELI5: Use DesignCenter to copy the current drawing and paste
              it as a new file. Now you have two identical drawings
              that can diverge — one stays conservative, one gets
              wild experimental edits.
        """
        child = ContextSession(
            session_id=str(uuid.uuid4())[:12],
            name=new_name,
            created_at=time.time(),
            last_active=time.time(),
            current_state=self.current_state.copy(),
            branch_depth=self.branch_depth + 1,
            max_checkpoints=self.max_checkpoints,
        )
        # Copy checkpoints so the child has full history.
        child.checkpoints = [cp.model_copy() for cp in self.checkpoints]
        return child

    def prune_old_checkpoints(self, max_age_seconds: float) -> int:
        """
        ELI5: Like running AUDIT and PURGE on a bloated drawing.
              Old viewports that nobody has looked at in hours get
              deleted to keep the file size manageable.
        """
        now = time.time()
        before = len(self.checkpoints)
        self.checkpoints = [
            cp for cp in self.checkpoints
            if (now - cp.created_at) < max_age_seconds
        ]
        return before - len(self.checkpoints)


class ContextManager:
    """
    Master viewport manager for all active sessions.

    ELI5: This is the Sheet Set Manager in AutoCAD. It keeps track
          of every open drawing (session), every saved view
          (checkpoint), and every copy-for-what-if (branch).
          Even if a drafting station crashes, the Sheet Set
          Manager knows exactly where every drawing left off.
    """

    def __init__(self, persist_dir: Optional[Path] = None) -> None:
        self.sessions: Dict[str, ContextSession] = {}
        self._lock = asyncio.Lock()
        self.persist_dir = persist_dir or Path("context_checkpoints")
        self.persist_dir.mkdir(parents=True, exist_ok=True)

    async def create_session(self, name: str) -> ContextSession:
        """Start a new drawing file in the Sheet Set."""
        async with self._lock:
            session = ContextSession(name=name)
            self.sessions[session.session_id] = session
            return session

    async def get_session(self, session_id: str) -> Optional[ContextSession]:
        """Open an existing drawing by its file name."""
        async with self._lock:
            session = self.sessions.get(session_id)
            if session:
                session.touch()
            return session

    async def checkpoint(self, session_id: str, label: str) -> Optional[Checkpoint]:
        """Save a viewport snapshot of the current drawing."""
        async with self._lock:
            session = self.sessions.get(session_id)
            if not session:
                return None
            cp = session.add_checkpoint(label, session.current_state)
            await self._persist_session(session)
            return cp

    async def restore(self, session_id: str, checkpoint_id: str) -> bool:
        """Restore a drawing to a previously saved viewport."""
        async with self._lock:
            session = self.sessions.get(session_id)
            if not session:
                return False
            ok = session.restore_checkpoint(checkpoint_id)
            if ok:
                await self._persist_session(session)
            return ok

    async def branch_session(self, session_id: str, new_name: str) -> Optional[ContextSession]:
        """Make a copy of a drawing for experimental edits."""
        async with self._lock:
            parent = self.sessions.get(session_id)
            if not parent:
                return None
            child = parent.branch(new_name)
            self.sessions[child.session_id] = child
            await self._persist_session(child)
            return child

    async def list_sessions(self) -> List[ContextSession]:
        """Show every open drawing in the Sheet Set Manager."""
        async with self._lock:
            return list(self.sessions.values())

    async def delete_session(self, session_id: str) -> bool:
        """Close a drawing and remove it from the Sheet Set."""
        async with self._lock:
            session = self.sessions.pop(session_id, None)
            if session:
                path = self.persist_dir / f"{session_id}.json"
                if path.exists():
                    path.unlink()
            return session is not None

    async def prune(self, max_age_seconds: float = 3600) -> int:
        """Purge old viewports across all drawings."""
        total = 0
        async with self._lock:
            for session in self.sessions.values():
                total += session.prune_old_checkpoints(max_age_seconds)
                await self._persist_session(session)
        return total

    async def recover_all(self) -> int:
        """
        ELI5: AutoCAD crashed? No problem. The Drawing Recovery Manager
              scans the backup folder and rebuilds the Sheet Set
              from every .sv$ and .bak file it finds.
        """
        count = 0
        if not self.persist_dir.exists():
            return 0

        for path in self.persist_dir.glob("*.json"):
            try:
                async with aiofiles.open(path, "r", encoding="utf-8") as f:
                    raw = await f.read()
                data = json.loads(raw)
                session = ContextSession(**data)
                # Rebuild checkpoints from raw dicts
                session.checkpoints = [Checkpoint(**c) for c in data.get("checkpoints", [])]
                self.sessions[session.session_id] = session
                count += 1
            except Exception:
                continue
        return count

    async def _persist_session(self, session: ContextSession) -> None:
        """Write a drawing file to disk — the SAVE command."""
        path = self.persist_dir / f"{session.session_id}.json"
        raw = session.model_dump_json(indent=2)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(raw)
