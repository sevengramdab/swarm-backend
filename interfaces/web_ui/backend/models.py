#!/usr/bin/env python3
"""
models.py
=========
Pydantic request/response models for all FastAPI endpoints.

ELI5: Like the standardized symbols on an electrical drawing.
      Every switch, outlet, and breaker has a specific symbol
      (model) so any electrician reading the blueprint knows
      exactly what component to install.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SwarmStatusResponse(BaseModel):
    running: bool
    agents_total: int
    agents_active: int
    agents_idle: int
    pending_tasks: int
    completed_tasks: int
    failed_tasks: int
    uptime_seconds: float


class AgentActionRequest(BaseModel):
    agent_id: str
    action: str  # kill, reallocate, pause, resume


class AgentActionResponse(BaseModel):
    success: bool
    message: str
    agent_id: str


class NodeHealthResponse(BaseModel):
    node_id: str
    status: str
    gpu_utilization: Optional[float] = None
    vram_used_mb: Optional[int] = None
    vram_total_mb: Optional[int] = None
    latency_ms: float
    last_seen: float


class RoutingConfigResponse(BaseModel):
    mode: str
    threshold: float
    healthy_tiers: List[str]
    tripped_tiers: List[str]


class SetThresholdRequest(BaseModel):
    threshold: float = Field(ge=0.0, le=1.0)


class ChatMessage(BaseModel):
    role: str  # system, user, assistant
    content: str


class InferRequest(BaseModel):
    prompt: str
    model_hint: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    expected_output_tokens: int = 256
    image_attachments: int = 0
    audio_attachments: int = 0
    requires_reasoning: bool = False
    requires_tools: bool = False
    latency_sensitive: bool = False
    cost_sensitive: bool = True
    messages: Optional[List[ChatMessage]] = None  # conversation history
    mode: str = "agent"  # agent, plan, research, swarm_code, debug, auto


class InferResponse(BaseModel):
    request_id: str
    tier: str
    node_id: Optional[str] = None
    model: Optional[str] = None
    complexity_score: float
    reason: str
    estimated_cost: float
    estimated_latency_ms: float
    task_id: Optional[str] = None


class TelemetryEvent(BaseModel):
    event_type: str
    timestamp: float
    payload: Dict[str, Any]


class TelemetrySummary(BaseModel):
    total_events: int
    events_last_hour: int
    top_agents: List[Dict[str, Any]]
    top_event_types: List[Dict[str, Any]]


class SITKTransferStatus(BaseModel):
    transfer_id: str
    payload_name: str
    target_node: str
    progress_percent: float
    bytes_transferred: int
    bytes_total: int
    status: str  # pending, transferring, completed, failed
    eta_seconds: Optional[float] = None


class CommandResponse(BaseModel):
    command: str
    result: str
    success: bool
