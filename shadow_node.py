"""
shadow_node.py
================
Simulates the Shadow PC (RTX 3080, 10GB VRAM) for distributed testing.
Runs on port 8002 with its own workspace.
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from core.simpleswarm.swarm_coder import SwarmCoder
from interfaces.web_ui.backend.routers.remote import router as remote_router

app = FastAPI(title="SimplePod Shadow PC (RTX 3080)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(remote_router)

# Shadow PC workspace
SHADOW_WORKSPACE = os.path.join(PROJECT_ROOT, "shadow_workspace")
os.makedirs(SHADOW_WORKSPACE, exist_ok=True)

_coder = SwarmCoder(project_dir=SHADOW_WORKSPACE)


class SubmitTaskRequest(BaseModel):
    goal: str


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "simplepod-shadow-pc",
        "node_id": "shadow_pc",
        "gpu": "rtx_3080",
        "vram_mb": 10240,
        "models": ["dolphin-mixtral:latest", "mixtral:8x7b", "solar:latest", "openchat:latest", "dolphin-llama3:latest"],
    }


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
    return {"data": {"models": ["dolphin-mixtral:latest", "mixtral:8x7b", "solar:latest", "openchat:latest", "dolphin-llama3:latest"]}}


@app.get("/simpleswarm/nodes/metrics")
def get_metrics():
    return {"data": {"gpu_utilization": 25.0, "vram_used_mb": 6144, "vram_total_mb": 10240}}


if __name__ == "__main__":
    print("[SHADOW PC] Starting Shadow PC simulator (RTX 3080, 10GB VRAM) on port 8002...")
    print("[SHADOW PC] Workspace:", SHADOW_WORKSPACE)
    uvicorn.run(app, host="0.0.0.0", port=8002)
