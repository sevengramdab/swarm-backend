#!/usr/bin/env python3
"""
routers/swarm.py
================
Swarm control endpoints.

ELI5: These are the light switches on the wall.
      `POST /swarm/activate` = flip the master switch ON.
      `POST /swarm/shutdown` = flip the master switch OFF.
      `GET /swarm/status` = read the smart meter.
      `POST /swarm/agents/{id}/kill` = trip one breaker manually.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..dependencies import get_swarm_orchestrator
from ..models import AgentActionRequest, AgentActionResponse, SwarmStatusResponse

router = APIRouter(prefix="/swarm", tags=["swarm"])


class SpawnAgentsRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=50, description="Number of agents to spawn")
    model: Optional[str] = Field(default=None, description="Preferred model for these agents")
    config: Optional[Dict[str, Any]] = Field(default=None, description="Per-agent config dict")


class SpawnAgentsResponse(BaseModel):
    success: bool
    spawned: List[str]
    message: str


class AgentConfigUpdate(BaseModel):
    config: Dict[str, Any]


@router.post("/activate")
async def activate_swarm(orch=Depends(get_swarm_orchestrator)) -> dict:
    """Flip the master switch ON."""
    if hasattr(orch, "start"):
        orch.start()
    return {"status": "activated"}


@router.post("/shutdown")
async def shutdown_swarm(orch=Depends(get_swarm_orchestrator)) -> dict:
    """Flip the master switch OFF."""
    if hasattr(orch, "shutdown"):
        orch.shutdown()
    return {"status": "shutting_down"}


@router.get("/status", response_model=SwarmStatusResponse)
async def swarm_status(orch=Depends(get_swarm_orchestrator)) -> SwarmStatusResponse:
    """Read the smart meter."""
    if hasattr(orch, "status"):
        raw = orch.status()
        return SwarmStatusResponse(**raw)
    raise HTTPException(status_code=503, detail="Orchestrator status unavailable")


@router.get("/agents")
async def list_agents(orch=Depends(get_swarm_orchestrator)) -> list:
    """List every worker on the job site."""
    if hasattr(orch, "agents"):
        return list(orch.agents.values())
    return []


@router.get("/agents/{agent_id}")
async def get_agent_detail(agent_id: str, orch=Depends(get_swarm_orchestrator)) -> dict:
    """Read the full work log for one worker."""
    if hasattr(orch, "_orch"):
        state = orch._orch.agents.get(agent_id)
        if not state:
            raise HTTPException(status_code=404, detail="Agent not found")
        return {
            "agent_id": state.agent_id,
            "status": "running" if state.task else ("idle" if state.alive else "dead"),
            "alive": state.alive,
            "shutdown": state.shutdown,
            "tasks_completed": state.tasks_completed,
            "tasks_failed": state.tasks_failed,
            "spawned_at": state.spawned_at,
            "uptime_seconds": round(__import__('time').time() - state.spawned_at, 1),
            "last_heartbeat": state.last_heartbeat,
            "current_task": {
                "task_id": state.task.id,
                "status": state.task.status.name if hasattr(state.task.status, 'name') else str(state.task.status),
                "prompt": (state.task.payload or {}).get("prompt", "")[:200] if state.task else None,
                "model": (state.task.payload or {}).get("model", "") if state.task else None,
                "started_at": state.task.started_at,
            } if state.task else None,
        }
    raise HTTPException(status_code=501, detail="Agent detail not available")


@router.post("/agents/spawn", response_model=SpawnAgentsResponse)
async def spawn_agents(req: SpawnAgentsRequest, orch=Depends(get_swarm_orchestrator)) -> SpawnAgentsResponse:
    """Hire new workers."""
    spawned = []
    if hasattr(orch, "_orch"):
        for _ in range(req.count):
            agent_id = orch._orch._spawn_agent()
            if agent_id:
                spawned.append(agent_id)
                # Apply initial config if provided
                if req.config and hasattr(orch, "_set_agent_config"):
                    orch._set_agent_config(agent_id, req.config)
        return SpawnAgentsResponse(
            success=len(spawned) > 0,
            spawned=spawned,
            message=f"Spawned {len(spawned)} agent(s)" + (f" (capped by max_agents)" if len(spawned) < req.count else ""),
        )
    raise HTTPException(status_code=501, detail="Spawn not available")


@router.post("/agents/{agent_id}/kill", response_model=AgentActionResponse)
async def kill_agent(agent_id: str, orch=Depends(get_swarm_orchestrator)) -> AgentActionResponse:
    """Manually trip one worker's breaker."""
    if hasattr(orch, "_kill_agent"):
        orch._kill_agent(agent_id, reason="api_request")
        return AgentActionResponse(success=True, message=f"Agent {agent_id} killed", agent_id=agent_id)
    raise HTTPException(status_code=501, detail="Kill not implemented")


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str, orch=Depends(get_swarm_orchestrator)) -> dict:
    """Remove a dead agent from the registry."""
    if hasattr(orch, "_remove_agent"):
        removed = orch._remove_agent(agent_id)
        if removed:
            return {"success": True, "message": f"Agent {agent_id} removed", "agent_id": agent_id}
        raise HTTPException(status_code=400, detail="Agent is still alive or not found. Kill it first.")
    raise HTTPException(status_code=501, detail="Remove not implemented")


@router.put("/agents/{agent_id}/config")
async def update_agent_config(agent_id: str, req: AgentConfigUpdate, orch=Depends(get_swarm_orchestrator)) -> dict:
    """Update per-agent configuration (model, temperature, etc.)."""
    if hasattr(orch, "_set_agent_config"):
        ok = orch._set_agent_config(agent_id, req.config)
        if ok:
            return {"success": True, "agent_id": agent_id, "config": req.config}
        raise HTTPException(status_code=404, detail="Agent not found")
    raise HTTPException(status_code=501, detail="Config update not implemented")


@router.get("/agents/{agent_id}/config")
async def get_agent_config(agent_id: str, orch=Depends(get_swarm_orchestrator)) -> dict:
    """Get per-agent configuration."""
    if hasattr(orch, "get_agent_config"):
        cfg = orch.get_agent_config(agent_id)
        if cfg is not None:
            return {"success": True, "agent_id": agent_id, "config": cfg}
        raise HTTPException(status_code=404, detail="Agent not found")
    raise HTTPException(status_code=501, detail="Config read not implemented")


@router.post("/agents/{agent_id}/reallocate", response_model=AgentActionResponse)
async def reallocate_agent(agent_id: str, orch=Depends(get_swarm_orchestrator)) -> AgentActionResponse:
    """Move a worker to a different trailer."""
    return AgentActionResponse(success=False, message="Reallocation requires controller integration", agent_id=agent_id)


@router.get("/tasks/active")
async def get_active_tasks(orch=Depends(get_swarm_orchestrator)) -> list:
    """List all tasks currently being processed by agents."""
    if hasattr(orch, "get_active_tasks"):
        return orch.get_active_tasks()
    return []


@router.get("/tasks/{task_id}")
async def get_task_result(task_id: str, orch=Depends(get_swarm_orchestrator)) -> dict:
    """Fetch the result of a specific task."""
    if hasattr(orch, "get_task_result"):
        result = orch.get_task_result(task_id)
        if result:
            return result
    raise HTTPException(status_code=404, detail="Task not found or not yet completed")


@router.get("/models")
async def list_models(orch=Depends(get_swarm_orchestrator)) -> list:
    """List available LLM models."""
    from ..settings_store import get_setting
    if hasattr(orch, "list_models"):
        return orch.list_models()
    return get_setting('default_model', 'llama3.2').split(',')
