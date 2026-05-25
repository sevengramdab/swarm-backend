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


class PlanRequest(BaseModel):
    goal: str


class ExecutePlanRequest(BaseModel):
    option_id: str


class ReactTaskRequest(BaseModel):
    goal: str


# ---------------------------------------------------------------------------
# Standard Task Endpoints
# ---------------------------------------------------------------------------

@router.post("/task", response_model=TaskResponse)
async def submit_task(req: SubmitTaskRequest) -> Dict[str, Any]:
    """Submit a new autonomous coding goal."""
    coder = _get_coder()
    task = coder.submit_task(req.goal)
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


# ---------------------------------------------------------------------------
# Plan Creator Endpoints
# ---------------------------------------------------------------------------

@router.post("/plan")
async def create_plan(req: PlanRequest) -> Dict[str, Any]:
    """Create a multi-option plan for a goal. Returns options to choose from."""
    coder = _get_coder()
    plan = coder.create_plan(req.goal)
    return coder.plan_creator.to_dict(plan)


@router.get("/plan/{plan_id}")
async def get_plan(plan_id: str) -> Dict[str, Any]:
    """Get the current status of a plan."""
    coder = _get_coder()
    plan = coder.get_plan(plan_id)
    if plan is None:
        return {"error": f"Plan {plan_id} not found"}
    return coder.plan_creator.to_dict(plan)


@router.post("/plan/{plan_id}/execute")
async def execute_plan(plan_id: str, req: ExecutePlanRequest) -> Dict[str, Any]:
    """Execute a chosen plan option as a new task."""
    coder = _get_coder()
    task = coder.execute_plan(plan_id, req.option_id)
    if task is None:
        return {"error": f"Could not execute plan {plan_id} with option {req.option_id}"}
    return coder.to_dict(task)


# ---------------------------------------------------------------------------
# ReAct Agent Endpoints
# ---------------------------------------------------------------------------

@router.post("/react/task")
async def submit_react_task(req: ReactTaskRequest) -> Dict[str, Any]:
    """Submit a goal to the ReAct multi-turn agent."""
    coder = _get_coder()
    task = coder.submit_react_task(req.goal)
    import asyncio
    await asyncio.sleep(0.5)
    return coder.react_agent.to_dict(task)


@router.get("/react/task/{task_id}")
async def get_react_task(task_id: str) -> Dict[str, Any]:
    """Get the current status of a ReAct task."""
    coder = _get_coder()
    task = coder.get_react_task(task_id)
    if task is None:
        return {"error": f"ReAct task {task_id} not found"}
    return coder.react_agent.to_dict(task)


@router.get("/react/tasks")
async def list_react_tasks() -> Dict[str, Any]:
    """List all ReAct tasks (most recent first)."""
    coder = _get_coder()
    tasks = [coder.react_agent.to_dict(t) for t in coder.list_react_tasks()]
    return {"tasks": tasks}


@router.post("/react/task/{task_id}/stop")
async def stop_react_task(task_id: str) -> Dict[str, Any]:
    """Stop a running ReAct task."""
    coder = _get_coder()
    ok = coder.stop_react_task(task_id)
    return {"success": ok, "task_id": task_id}
