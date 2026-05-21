"""
Twilio MMS Gateway Interface — Command Parser

Think of this like a smart voice assistant for your home automation.
When Mom says "Turn off the living room lights" or "Is the garage closed?",
the assistant needs to understand what she WANTS, not just the exact words.
This file is the brain that turns messy human talk into clean little
instruction cards the robots can read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


# =============================================================================
# Command Types — Like labeled sticky notes
# =============================================================================

class CommandAction(str, Enum):
    """
    These are the only sticky-note colors Mom can use.
    Each color means a different chore around the house.
    """
    STATUS = "status"
    AGENTS = "agents"
    NODES = "nodes"
    BREAKER = "breaker"
    STOP = "stop"
    PICTURE = "picture"
    HELP = "help"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    """
    This is the cleaned-up instruction card.
    It tells the house robot: WHAT to do, and maybe WHERE to do it.
    """
    action: str
    target: str | None
    raw_input: str
    confidence: float = 1.0


# =============================================================================
# Keyword Maps — Like a cheat sheet on the fridge
# =============================================================================

class CommandParser:
    """
    This is the brain that reads Mom's texts.
    It looks for special words (like secret codes) and figures out
    which chore Mom wants done.
    """

    # --- Status: "What's going on?" ---
    STATUS_KEYWORDS: Iterable[str] = (
        "status", "state", "how are you", "how's it going",
        "report", "summary", "overview", "health", "check",
        "whats up", "what's up", "how is everything",
    )

    # --- Agents: "Who's working?" ---
    AGENTS_KEYWORDS: Iterable[str] = (
        "agents", "workers", "bots", "who is on", "who's on",
        "crew", "team", "squad", "active agents",
    )

    # --- Nodes: "Which rooms are on?" ---
    NODES_KEYWORDS: Iterable[str] = (
        "nodes", "servers", "rooms", "devices", "machines",
        "units", "systems", "connected nodes",
    )

    # --- Breaker: "Flip the switch" ---
    BREAKER_KEYWORDS: Iterable[str] = (
        "breaker", "switch", "toggle", "flip",
        "circuit", "disconnect", "reconnect",
        "local", "cloud", "on prem", "on-prem",
    )

    # --- Stop: "Emergency brake!" ---
    STOP_KEYWORDS: Iterable[str] = (
        "stop", "halt", "pause", "kill", "shutdown",
        "abort", "cease", "end", "terminate",
    )

    # --- Picture: "Show me the camera feed" ---
    PICTURE_KEYWORDS: Iterable[str] = (
        "picture", "pic", "image", "photo", "chart",
        "graph", "visual", "screenshot", "snapshot",
        "show me", "send me a pic",
    )

    # --- Help: "I forgot the instructions" ---
    HELP_KEYWORDS: Iterable[str] = (
        "help", "commands", "what can i do", "instructions",
        "menu", "options", "list", "how do i",
    )

    def __init__(self) -> None:
        """
        Set up the brain. It's like putting the cheat sheet on the fridge
        so we can read it whenever a text comes in.
        """
        self._compiled_patterns = self._compile_patterns()

    def _compile_patterns(self) -> dict[str, re.Pattern[str]]:
        """
        This is like laminating the cheat sheet so it lasts longer.
        We turn the word lists into fast search tools.
        """
        return {
            CommandAction.STATUS.value: self._make_pattern(self.STATUS_KEYWORDS),
            CommandAction.AGENTS.value: self._make_pattern(self.AGENTS_KEYWORDS),
            CommandAction.NODES.value: self._make_pattern(self.NODES_KEYWORDS),
            CommandAction.BREAKER.value: self._make_pattern(self.BREAKER_KEYWORDS),
            CommandAction.STOP.value: self._make_pattern(self.STOP_KEYWORDS),
            CommandAction.PICTURE.value: self._make_pattern(self.PICTURE_KEYWORDS),
            CommandAction.HELP.value: self._make_pattern(self.HELP_KEYWORDS),
        }

    @staticmethod
    def _make_pattern(keywords: Iterable[str]) -> re.Pattern[str]:
        """
        Turn a list of words into a super-fast search tool.
        It's like creating a magnet that only sticks to certain words.
        """
        escaped = [re.escape(kw) for kw in keywords]
        pattern = r"(?:^|\s)(" + "|".join(escaped) + r")(?:\s|$|[.,!?])"
        return re.compile(pattern, re.IGNORECASE)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def parse(self, raw_text: str) -> ParsedCommand:
        """
        This is the main desk where Mom's text lands.
        We read it, check the cheat sheet, and hand back a clean
        instruction card for the robot butler.
        """
        cleaned = raw_text.strip().lower()

        if not cleaned:
            return ParsedCommand(
                action=CommandAction.UNKNOWN.value,
                target=None,
                raw_input=raw_text,
                confidence=0.0,
            )

        # Check each color of sticky note to see which matches best
        for action, pattern in self._compiled_patterns.items():
            if pattern.search(cleaned):
                target = self._extract_target(cleaned, action)
                return ParsedCommand(
                    action=action,
                    target=target,
                    raw_input=raw_text,
                    confidence=1.0,
                )

        # Nothing matched — hand back a confused sticky note
        return ParsedCommand(
            action=CommandAction.UNKNOWN.value,
            target=None,
            raw_input=raw_text,
            confidence=0.0,
        )

    def _extract_target(self, text: str, action: str) -> str | None:
        """
        Sometimes Mom says "Turn off the KITCHEN lights."
        This figures out WHICH room (target) she means.
        It's like reading the label on the light switch.
        """
        if action == CommandAction.BREAKER.value:
            # Look for "local" or "cloud" nearby
            if "local" in text or "on prem" in text or "on-prem" in text:
                return "local"
            if "cloud" in text:
                return "cloud"
            return None

        if action == CommandAction.STOP.value:
            # Look for an agent name or "all" after stop words
            tokens = text.split()
            stop_idx: int | None = None
            for idx, token in enumerate(tokens):
                if token in self.STOP_KEYWORDS:
                    stop_idx = idx
                    break
            if stop_idx is not None and stop_idx + 1 < len(tokens):
                return tokens[stop_idx + 1]
            return "all"

        return None

    def is_command(self, raw_text: str) -> bool:
        """
        Quick peek: Is this text a real command, or just Mom saying hi?
        It's like glancing at a note to see if it's a grocery list
        or just a doodle.
        """
        result = self.parse(raw_text)
        return result.action != CommandAction.UNKNOWN.value
