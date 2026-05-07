"""Token usage tracking for swarm sessions."""

import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Rough heuristic: ~4 characters per token for English text
CHARS_PER_TOKEN = 4.0


class TokenUsage:
    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.requests = 0

    def add(self, input_chars: int = 0, output_chars: int = 0, input_tokens: int = 0, output_tokens: int = 0):
        """Add usage. If token counts not provided, estimates from character counts."""
        inp = input_tokens or int(input_chars / CHARS_PER_TOKEN)
        out = output_tokens or int(output_chars / CHARS_PER_TOKEN)
        self.input_tokens += inp
        self.output_tokens += out
        self.total_tokens = self.input_tokens + self.output_tokens
        self.requests += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "requests": self.requests,
        }


class TokenTracker:
    """Global token tracker per session."""

    def __init__(self):
        self._sessions: Dict[str, TokenUsage] = {}

    def get(self, session_id: str) -> TokenUsage:
        if session_id not in self._sessions:
            self._sessions[session_id] = TokenUsage()
        return self._sessions[session_id]

    def add(
        self,
        session_id: str,
        input_chars: int = 0,
        output_chars: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ):
        usage = self.get(session_id)
        usage.add(
            input_chars=input_chars,
            output_chars=output_chars,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        logger.debug(f"[TokenTracker] {session_id}: {usage.to_dict()}")

    def reset(self, session_id: str):
        self._sessions[session_id] = TokenUsage()

    def to_dict(self, session_id: str) -> Dict[str, Any]:
        return self.get(session_id).to_dict()


# Global singleton
tracker = TokenTracker()
