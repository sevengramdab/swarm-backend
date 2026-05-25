"""
SWARM CODER ROUTER
==================
API for the autonomous coding agent.
Submit a goal, watch it plan and execute, review results.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter
from pydantic import BaseModel

import sys
import os

# Ensure core is importable
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.simpleswarm.swarm_coder import SwarmCoder

router = APIRouter(prefix="/swarmcoder", tags=["swarmcoder"])

# Singleton SwarmCoder instance
_coder: Optional[SwarmCoder] = None


def _get_coder() -> SwarmCoder:
    global _coder
    if _coder is None:
        _coder = SwarmCoder(project_dir=_PROJECT_ROOT)
    return _coder


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SubmitTaskRequest(BaseModel):
    goal: str


class TaskResponse(BaseModel):
    task_id: str
    goal: str
    status: str
    current_step: int
    total_steps: int
    created_at: float
    updated_at: float
    result_summary: str
    logs: List[Dict[str, Any]]


class TaskListResponse(BaseModel):
    tasks: List[TaskResponse]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/task", response_model=TaskResponse)
async def submit_task(req: SubmitTaskRequest) -> Dict[str, Any]:
    """Submit a new autonomous coding goal."""
    coder = _get_coder()
    task = coder.submit_task(req.goal)
    # Wait a moment for planning to start
    import asyncio
    await asyncio.sleep(0.5)
    return coder.to_dict(task)


@router.get("/task/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str) -> Dict[str, Any]:
    """Get the current status of a task."""
    coder = _get_coder()
    task = coder.get_task(task_id)
    if task is None:
        return {"error": f"Task {task_id} not found"}
    return coder.to_dict(task)


@router.post("/task/{task_id}/stop")
async def stop_task(task_id: str) -> Dict[str, Any]:
    """Stop a running task."""
    coder = _get_coder()
    ok = coder.stop_task(task_id)
    return {"success": ok, "task_id": task_id}


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks() -> Dict[str, Any]:
    """List all tasks (most recent first)."""
    coder = _get_coder()
    tasks = [coder.to_dict(t) for t in coder.list_tasks()]
    return {"tasks": tasks}


class ActionRequest(BaseModel):
    action: str
    params: Dict[str, Any] = {}

@router.post("/action")
async def direct_action(req: ActionRequest) -> Dict[str, Any]:
    """Execute a single FileSystem or Shell action directly (for debugging)."""
    coder = _get_coder()
    from core.simpleswarm.swarm_coder import Step
    step = Step(step_number=0, action=req.action, params=req.params)
    result = coder.executor.execute(step)
    return result
