"""
In-memory session store for agent loops awaiting user approvals or tool results.
"""

import asyncio
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from core.autonomy_engine import ToolResult
from core.change_tracker import ChangeBatch


@dataclass
class Session:
    session_id: str
    autonomy_level: str = "default"
    messages: list = field(default_factory=list)
    # Pending approvals
    approval_events: Dict[str, asyncio.Event] = field(default_factory=dict)
    approval_results: Dict[str, bool] = field(default_factory=dict)
    # Pending tool results
    tool_events: Dict[str, asyncio.Event] = field(default_factory=dict)
    tool_results: Dict[str, ToolResult] = field(default_factory=dict)
    # Pending decisions
    decision_events: Dict[str, asyncio.Event] = field(default_factory=dict)
    decision_results: Dict[str, str] = field(default_factory=dict)
    # Steering messages (user-injected mid-task instructions)
    steering_messages: List[str] = field(default_factory=list)
    # Change tracking
    change_batches: List[ChangeBatch] = field(default_factory=list)


class SessionStore:
    """Simple in-memory store for active agent sessions."""

    def __init__(self):
        self._sessions: Dict[str, Session] = {}

    def create(self, session_id: str, autonomy_level: str = "default") -> Session:
        session = Session(session_id=session_id, autonomy_level=autonomy_level)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def remove(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def push_steering(self, session_id: str, message: str) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.steering_messages.append(message)
        return True

    def pop_steering(self, session_id: str) -> Optional[str]:
        session = self._sessions.get(session_id)
        if not session or not session.steering_messages:
            return None
        return session.steering_messages.pop(0)

    def compact(self, session_id: str, summary: str = "") -> dict:
        """Compact a session: summarize messages and clear old state."""
        session = self._sessions.get(session_id)
        if not session:
            return {"ok": False, "error": "Session not found"}

        old_count = len(session.messages)
        # Build a compact summary from existing messages
        if not summary and session.messages:
            # Keep the first system message and last 2 exchanges, summarize the rest
            summary_parts = []
            for msg in session.messages:
                if isinstance(msg, dict) and msg.get("role") == "user":
                    content = msg.get("content", "")
                    if len(content) > 100:
                        content = content[:100] + "..."
                    summary_parts.append(f"User asked: {content}")
                elif isinstance(msg, dict) and msg.get("role") == "assistant":
                    content = msg.get("content", "")
                    if len(content) > 100:
                        content = content[:100] + "..."
                    summary_parts.append(f"Assistant: {content}")
            summary = "\n".join(summary_parts[-6:]) if summary_parts else "Session started."

        # Replace messages with compact summary
        session.messages = [
            {"role": "system", "content": f"[COMPACTED CONTEXT] Previous conversation summary:\n{summary}"},
            {"role": "assistant", "content": "Context compacted. Ready to continue."}
        ]

        # Clear pending events to free memory
        session.approval_events.clear()
        session.approval_results.clear()
        session.tool_events.clear()
        session.tool_results.clear()
        session.decision_events.clear()
        session.decision_results.clear()

        return {
            "ok": True,
            "session_id": session_id,
            "old_message_count": old_count,
            "new_message_count": len(session.messages),
            "summary": summary,
        }

    def add_change_batch(self, session_id: str, batch: ChangeBatch) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.change_batches.append(batch)
        return True

    def get_change_batches(self, session_id: str) -> List[ChangeBatch]:
        session = self._sessions.get(session_id)
        if not session:
            return []
        return list(session.change_batches)

    def get_latest_change_batch(self, session_id: str) -> Optional[ChangeBatch]:
        session = self._sessions.get(session_id)
        if not session or not session.change_batches:
            return None
        return session.change_batches[-1]

    def set_approval(self, session_id: str, request_id: str, approved: bool) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.approval_results[request_id] = approved
        event = session.approval_events.get(request_id)
        if event:
            event.set()
        return True

    def set_tool_result(self, session_id: str, request_id: str, result: ToolResult) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.tool_results[request_id] = result
        event = session.tool_events.get(request_id)
        if event:
            event.set()
        return True

    def set_decision(self, session_id: str, request_id: str, decision: str) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.decision_results[request_id] = decision
        event = session.decision_events.get(request_id)
        if event:
            event.set()
        return True

    async def wait_for_approval(self, session_id: str, request_id: str, context: dict) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        # Fast path: result already arrived
        if request_id in session.approval_results:
            return session.approval_results.pop(request_id)
        event = asyncio.Event()
        session.approval_events[request_id] = event
        await event.wait()
        return session.approval_results.pop(request_id, False)

    async def wait_for_tool_result(self, session_id: str, request_id: str, context: dict) -> ToolResult:
        session = self._sessions.get(session_id)
        if not session:
            return ToolResult("", {}, "error", error="Session not found")
        # Fast path: result already arrived
        if request_id in session.tool_results:
            return session.tool_results.pop(request_id)
        event = asyncio.Event()
        session.tool_events[request_id] = event
        await event.wait()
        return session.tool_results.pop(request_id, ToolResult("", {}, "error", error="No tool result received"))

    async def wait_for_decision(self, session_id: str, request_id: str, context: dict) -> str:
        session = self._sessions.get(session_id)
        if not session:
            return "skip"
        # Fast path: result already arrived
        if request_id in session.decision_results:
            return session.decision_results.pop(request_id)
        event = asyncio.Event()
        session.decision_events[request_id] = event
        await event.wait()
        return session.decision_results.pop(request_id, "skip")


# Global singleton
store = SessionStore()
