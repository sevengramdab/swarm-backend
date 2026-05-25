"""
remote_node.py
==============
Minimal SimplePod remote node for distributed testing.
Runs on a different port with its own workspace.
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List
import uvicorn

from core.simpleswarm.swarm_coder import SwarmCoder

app = FastAPI(title="SimplePod Remote Node")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Remote node workspace
REMOTE_WORKSPACE = os.path.join(PROJECT_ROOT, "remote_workspace")
os.makedirs(REMOTE_WORKSPACE, exist_ok=True)

_coder = SwarmCoder(project_dir=REMOTE_WORKSPACE)


class SubmitTaskRequest(BaseModel):
    goal: str


@app.get("/health")
def health():
    return {"status": "healthy", "service": "simplepod-remote-node", "node_id": "remote-test-01"}


@app.post("/swarmcoder/task")
def submit_task(req: SubmitTaskRequest):
    task = _coder.submit_task(req.goal)
    return {
        "task_id": task.task_id,
        "goal": task.goal,
        "status": task.status,
        "created_at": task.created_at,
    }


@app.get("/swarmcoder/task/{task_id}")
def get_task(task_id: str):
    task = _coder.get_task(task_id)
    if task is None:
        return {"error": f"Task {task_id} not found"}
    return _coder.to_dict(task)


@app.get("/swarmcoder/tasks")
def list_tasks():
    return {"tasks": [_coder.to_dict(t) for t in _coder.list_tasks()]}


@app.get("/simpleswarm/nodes/models")
def list_models():
    return {"data": {"models": ["llama3.2", "dolphin-llama3", "openchat", "solar"]}}


@app.get("/simpleswarm/nodes/metrics")
def get_metrics():
    return {"data": {"gpu_utilization": 15.0, "vram_used_mb": 2048, "vram_total_mb": 8192}}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
