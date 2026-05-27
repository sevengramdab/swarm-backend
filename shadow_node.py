"""
shadow_node.py
================
SimplePod Shadow Node — runs on the actual shadow PC.
Auto-detects GPU, Ollama models, and exposes remote-control endpoints.

Run on shadow PC:
    python shadow_node.py

Env overrides:
    SIMPOD_NODE_ID=shadow_pc
    SIMPOD_PORT=8000
    SIMPOD_OLLAMA_URL=http://localhost:11434
"""
import sys
import os
import json
import subprocess
import socket

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# ---------------------------------------------------------------------------
# GPU Auto-Detection (no extra deps required)
# ---------------------------------------------------------------------------
def _detect_gpu():
    """Auto-detect GPU info. Returns (gpu_name, vram_mb)."""
    gpu_name = "unknown"
    vram_mb = 0

    # 1. Try nvidia-smi
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            text=True, stderr=subprocess.DEVNULL, timeout=5
        )
        parts = out.strip().split(",")
        if len(parts) >= 2:
            gpu_name = parts[0].strip().lower().replace(" ", "_")
            vram_mb = int(float(parts[1].strip()))
            return gpu_name, vram_mb
    except Exception:
        pass

    # 2. Try GPUtil if installed
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            g = gpus[0]
            gpu_name = g.name.lower().replace(" ", "_")
            vram_mb = int(g.memoryTotal)
            return gpu_name, vram_mb
    except Exception:
        pass

    # 3. Try Windows WMI
    try:
        import wmi
        c = wmi.WMI()
        for gpu in c.Win32_VideoController():
            if gpu.AdapterRAM:
                gpu_name = gpu.Name.lower().replace(" ", "_")
                vram_mb = int(gpu.AdapterRAM) // (1024 * 1024)
                return gpu_name, vram_mb
    except Exception:
        pass

    return gpu_name, vram_mb


# ---------------------------------------------------------------------------
# Ollama Auto-Detection
# ---------------------------------------------------------------------------
def _fetch_ollama_models(ollama_url: str):
    """Fetch installed models from local Ollama."""
    try:
        import urllib.request
        req = urllib.request.Request(f"{ollama_url}/api/tags", method="GET")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            models = [m["name"] for m in data.get("models", [])]
            return models if models else ["none"]
    except Exception:
        return ["none"]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
NODE_ID = os.environ.get("SIMPOD_NODE_ID", "shadow_pc")
PORT = int(os.environ.get("SIMPOD_PORT", "8000"))
OLLAMA_URL = os.environ.get("SIMPOD_OLLAMA_URL", "http://localhost:11434")
GPU_NAME, VRAM_MB = _detect_gpu()
MODELS = _fetch_ollama_models(OLLAMA_URL)

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(title=f"SimplePod Shadow Node — {NODE_ID}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Remote control router (screenshot, click, type, etc.)
try:
    from interfaces.web_ui.backend.routers.remote import router as remote_router
    app.include_router(remote_router)
except Exception as e:
    print(f"[WARN] Remote control router not loaded: {e}")

# SwarmCoder router (optional — only if deps available)
_shadow_coder = None
SHADOW_WORKSPACE = os.path.join(PROJECT_ROOT, f"shadow_workspace_{NODE_ID}")
os.makedirs(SHADOW_WORKSPACE, exist_ok=True)

try:
    from core.simpleswarm.swarm_coder import SwarmCoder
    _shadow_coder = SwarmCoder(project_dir=SHADOW_WORKSPACE)
except Exception as e:
    print(f"[WARN] SwarmCoder not available: {e}")


class SubmitTaskRequest(BaseModel):
    goal: str


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "simplepod-shadow-node",
        "node_id": NODE_ID,
        "hostname": socket.gethostname(),
        "gpu": GPU_NAME,
        "vram_mb": VRAM_MB,
        "models": MODELS,
        "ollama_url": OLLAMA_URL,
    }


@app.post("/swarmcoder/task")
def submit_task(req: SubmitTaskRequest):
    if _shadow_coder is None:
        return {"error": "SwarmCoder not available on this node"}
    task = _shadow_coder.submit_task(req.goal)
    return {
        "task_id": task.task_id,
        "goal": task.goal,
        "status": task.status,
        "created_at": task.created_at,
    }


@app.get("/swarmcoder/task/{task_id}")
def get_task(task_id: str):
    if _shadow_coder is None:
        return {"error": "SwarmCoder not available"}
    task = _shadow_coder.get_task(task_id)
    if task is None:
        return {"error": f"Task {task_id} not found"}
    return _shadow_coder.to_dict(task)


@app.get("/swarmcoder/tasks")
def list_tasks():
    if _shadow_coder is None:
        return {"tasks": []}
    return {"tasks": [_shadow_coder.to_dict(t) for t in _shadow_coder.list_tasks()]}


@app.get("/simpleswarm/nodes/models")
def list_models():
    return {"data": {"models": MODELS}}


@app.get("/simpleswarm/nodes/metrics")
def get_metrics():
    # Try nvidia-smi for live metrics
    gpu_util = 0.0
    vram_used = 0
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
             "--format=csv,noheader,nounits"],
            text=True, stderr=subprocess.DEVNULL, timeout=3
        )
        parts = out.strip().split(",")
        if len(parts) >= 2:
            gpu_util = float(parts[0].strip())
            vram_used = int(float(parts[1].strip()))
    except Exception:
        pass
    return {
        "data": {
            "gpu_utilization": gpu_util,
            "vram_used_mb": vram_used,
            "vram_total_mb": VRAM_MB,
        }
    }


if __name__ == "__main__":
    print("=" * 60)
    print(f"  SimplePod Shadow Node — {NODE_ID}")
    print("=" * 60)
    print(f"  Hostname:  {socket.gethostname()}")
    print(f"  GPU:       {GPU_NAME}")
    print(f"  VRAM:      {VRAM_MB} MB")
    print(f"  Ollama:    {OLLAMA_URL}")
    print(f"  Models:    {MODELS}")
    print(f"  Workspace: {SHADOW_WORKSPACE}")
    print(f"  Port:      {PORT}")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=PORT)
