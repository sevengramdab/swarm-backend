"""
swarm.memory — Kimi 2.6 Advanced Memory & Stateful Context

The unified memory bus that keeps every agent's work alive across
ephemeral node lifecycles, just like a master template file in AutoCAD
that stores every layer, block, and viewport setting even when a
workstation crashes.
"""

from .memory_bus import MemoryBus, MemoryRecord
from .context_manager import ContextManager, ContextSession, Checkpoint
from .agent_registry import AgentRegistry, AgentRecord, AgentEvent
from .state_serializer import StateSerializer, CompressedState

__all__ = [
    "MemoryBus",
    "MemoryRecord",
    "ContextManager",
    "ContextSession",
    "Checkpoint",
    "AgentRegistry",
    "AgentRecord",
    "AgentEvent",
    "StateSerializer",
    "CompressedState",
]
