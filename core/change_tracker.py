"""
Change Tracker — Batched file-change tracking with diff, approval, and undo support.

Inspired by Copilot's multi-file diff review flow:
- Changes are captured as they happen
- Users review them in a batch after the agent finishes
- Approve/reject per-file or per-batch
- Full undo capability for applied changes
"""

import difflib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class ChangeStatus(str, Enum):
    PENDING = "pending"      # Awaiting review
    APPROVED = "approved"    # User approved, ready to apply
    REJECTED = "rejected"    # User rejected, will not apply
    APPLIED = "applied"      # Written to disk
    UNDONE = "undone"        # Was applied, then reverted


class BatchStatus(str, Enum):
    OPEN = "open"            # Still collecting changes
    REVIEWING = "reviewing"  # Presented to user for review
    APPLYING = "applying"    # In process of being applied
    APPLIED = "applied"      # All approved changes written
    REJECTED = "rejected"    # Entire batch rejected
    PARTIAL = "partial"      # Some approved, some rejected


@dataclass
class FileChange:
    """A single file modification."""
    change_id: str
    file_path: str
    original_content: Optional[str]  # None = file did not exist
    new_content: str
    status: ChangeStatus = ChangeStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def diff(self) -> str:
        """Unified diff of original → new."""
        original = self.original_content or ""
        lines_a = original.splitlines(keepends=True)
        lines_b = self.new_content.splitlines(keepends=True)
        # Ensure each line ends with newline for clean diff
        if lines_a and not lines_a[-1].endswith("\n"):
            lines_a[-1] += "\n"
        if lines_b and not lines_b[-1].endswith("\n"):
            lines_b[-1] += "\n"
        return "".join(
            difflib.unified_diff(
                lines_a,
                lines_b,
                fromfile=f"a/{self.file_path}",
                tofile=f"b/{self.file_path}",
            )
        )

    def summary(self) -> dict:
        return {
            "change_id": self.change_id,
            "file_path": self.file_path,
            "status": self.status.value,
            "is_new_file": self.original_content is None,
            "created_at": self.created_at,
        }

    def to_dict(self) -> dict:
        return {
            "change_id": self.change_id,
            "file_path": self.file_path,
            "original_content": self.original_content,
            "new_content": self.new_content,
            "status": self.status.value,
            "diff": self.diff(),
            "created_at": self.created_at,
        }


@dataclass
class ChangeBatch:
    """A collection of related file changes."""
    batch_id: str
    session_id: str
    title: str = "Agent Changes"
    changes: List[FileChange] = field(default_factory=list)
    status: BatchStatus = BatchStatus.OPEN
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None

    def add_change(self, file_path: str, original_content: Optional[str], new_content: str) -> FileChange:
        change = FileChange(
            change_id=str(uuid.uuid4())[:8],
            file_path=file_path,
            original_content=original_content,
            new_content=new_content,
        )
        self.changes.append(change)
        return change

    def get_change(self, change_id: str) -> Optional[FileChange]:
        for c in self.changes:
            if c.change_id == change_id:
                return c
        return None

    def approve(self, change_id: Optional[str] = None) -> bool:
        """Approve one change (by id) or all pending changes."""
        updated = False
        for c in self.changes:
            if change_id is None or c.change_id == change_id:
                if c.status == ChangeStatus.PENDING:
                    c.status = ChangeStatus.APPROVED
                    updated = True
        return updated

    def reject(self, change_id: Optional[str] = None) -> bool:
        """Reject one change (by id) or all pending changes."""
        updated = False
        for c in self.changes:
            if change_id is None or c.change_id == change_id:
                if c.status == ChangeStatus.PENDING:
                    c.status = ChangeStatus.REJECTED
                    updated = True
        return updated

    def mark_applied(self) -> None:
        self.status = BatchStatus.APPLIED
        self.completed_at = datetime.utcnow().isoformat()
        for c in self.changes:
            if c.status == ChangeStatus.APPROVED:
                c.status = ChangeStatus.APPLIED

    def mark_undone(self) -> None:
        for c in self.changes:
            if c.status == ChangeStatus.APPLIED:
                c.status = ChangeStatus.UNDONE
        self.status = BatchStatus.PARTIAL

    def stats(self) -> dict:
        counts = {s.value: 0 for s in ChangeStatus}
        for c in self.changes:
            counts[c.status.value] += 1
        return {
            "total": len(self.changes),
            "pending": counts[ChangeStatus.PENDING.value],
            "approved": counts[ChangeStatus.APPROVED.value],
            "rejected": counts[ChangeStatus.REJECTED.value],
            "applied": counts[ChangeStatus.APPLIED.value],
            "undone": counts[ChangeStatus.UNDONE.value],
        }

    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "session_id": self.session_id,
            "title": self.title,
            "status": self.status.value,
            "stats": self.stats(),
            "changes": [c.to_dict() for c in self.changes],
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class ChangeTracker:
    """Global change batch manager."""

    def __init__(self):
        self._batches: Dict[str, ChangeBatch] = {}

    def create_batch(self, session_id: str, title: str = "Agent Changes") -> ChangeBatch:
        batch = ChangeBatch(
            batch_id=str(uuid.uuid4())[:8],
            session_id=session_id,
            title=title,
        )
        self._batches[batch.batch_id] = batch
        return batch

    def get_batch(self, batch_id: str) -> Optional[ChangeBatch]:
        return self._batches.get(batch_id)

    def get_batches_for_session(self, session_id: str) -> List[ChangeBatch]:
        return [b for b in self._batches.values() if b.session_id == session_id]

    def get_open_batch(self, session_id: str) -> Optional[ChangeBatch]:
        """Return the most recent open batch for a session, or None."""
        batches = [b for b in self._batches.values()
                   if b.session_id == session_id and b.status == BatchStatus.OPEN]
        if not batches:
            return None
        return sorted(batches, key=lambda b: b.created_at, reverse=True)[0]

    def get_pending_review_batches(self, session_id: str) -> List[ChangeBatch]:
        return [b for b in self._batches.values()
                if b.session_id == session_id and b.status == BatchStatus.REVIEWING]

    def remove_batch(self, batch_id: str) -> bool:
        if batch_id in self._batches:
            del self._batches[batch_id]
            return True
        return False


# Global singleton
tracker = ChangeTracker()
