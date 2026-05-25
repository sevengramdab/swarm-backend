"""
simpleswarm.py
==============
FastAPI router for the SimpleSwarm autonomous computer control + test system.

Endpoints:
  POST /simpleswarm/test/start      -- Start the full 7-phase test
  GET  /simpleswarm/test/status     -- Check test progress
  GET  /simpleswarm/test/results    -- Get completed results
  POST /simpleswarm/test/stop       -- Stop running test
  POST /simpleswarm/action          -- Execute single computer action
  GET  /simpleswarm/screenshot      -- Capture desktop screenshot
  POST /simpleswarm/agents/spawn    -- Spawn N test agents

ELI5: The control panel for the robot inspector swarm.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/simpleswarm", tags=["simpleswarm"])

# Singleton orchestrator (lazy init)
_orchestrator = None

def _get_orch():
    global _orchestrator
    if _orchestrator is None:
        from core.simpleswarm.simple_swarm_orchestrator import SimpleSwarmOrchestrator
        _orchestrator = SimpleSwarmOrchestrator(max_agents=8)
    return _orchestrator


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

class StartTestRequest(BaseModel):
    parallel: bool = Field(default=True, description="Run API phases in parallel")
    include_destructive: bool = Field(default=False, description="Include Phase 6 (shutdown) and Phase 7 (cold start). WARNING: will kill the backend process.")


class ActionRequest(BaseModel):
    action: str = Field(..., description="Action name: click, click_rel, type_text, hotkey, press, "
                                         "screenshot, move_to, scroll, shell, open_browser, sleep")
    params: Dict[str, Any] = Field(default_factory=dict, description="Action-specific parameters")


class SpawnAgentsRequest(BaseModel):
    count: int = Field(default=4, ge=1, le=20, description="Number of agents to spawn")
    mode: str = Field(default="test", description="Agent mode: test, watchdog, api_only, ui_only")


class SimpleSwarmResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Test endpoints
# ---------------------------------------------------------------------------

@router.post("/test/start")
async def start_test(req: StartTestRequest):
    """Start the full 7-phase autonomous test suite."""
    orch = _get_orch()
    orch.skip_destructive = not req.include_destructive
    result = orch.start_test(parallel=req.parallel)
    if not result["success"]:
        raise HTTPException(status_code=409, detail=result["error"])
    return {"success": True, "message": "Test started", "parallel": req.parallel, "include_destructive": req.include_destructive}


@router.get("/test/status")
async def test_status():
    """Get current test progress."""
    orch = _get_orch()
    return orch.status()


@router.get("/test/results")
async def test_results():
    """Get all completed test results."""
    orch = _get_orch()
    return orch.get_results()


@router.post("/test/stop")
async def stop_test():
    """Stop a running test."""
    orch = _get_orch()
    return orch.stop_test()


# ---------------------------------------------------------------------------
# Single-action endpoint
# ---------------------------------------------------------------------------

@router.post("/action", response_model=SimpleSwarmResponse)
async def execute_action(req: ActionRequest):
    """
    Execute a single computer control action.
    Examples:
      {"action": "screenshot", "params": {}}
      {"action": "click_rel", "params": {"x_pct": 0.5, "y_pct": 0.5}}
      {"action": "type_text", "params": {"text": "hello"}}
      {"action": "hotkey", "params": {"keys": ["ctrl", "c"]}}
      {"action": "shell", "params": {"command": "echo hi"}}
      {"action": "open_browser", "params": {"url": "http://localhost:8000/orbstudio"}}
    """
    from core.simpleswarm.computer_controller import ComputerController

    cc = ComputerController()
    action = req.action
    p = req.params

    try:
        if action == "screenshot":
            res = cc.screenshot(save=True, filename=p.get("filename"))
        elif action == "click":
            res = cc.click(p["x"], p["y"], p.get("button", "left"), p.get("clicks", 1))
        elif action == "click_rel":
            res = cc.click_rel(p["x_pct"], p["y_pct"], p.get("button", "left"), p.get("clicks", 1))
        elif action == "type_text":
            res = cc.type_text(p["text"], p.get("interval", 0.01))
        elif action == "hotkey":
            res = cc.hotkey(*p["keys"])
        elif action == "press":
            res = cc.press(p["key"])
        elif action == "move_to":
            res = cc.move_to(p["x"], p["y"], p.get("duration", 0.25))
        elif action == "scroll":
            res = cc.scroll(p["clicks"], p.get("x"), p.get("y"))
        elif action == "shell":
            res = cc.shell(p["command"], p.get("cwd"), p.get("timeout", 30))
        elif action == "open_browser":
            res = cc.open_browser(p["url"], p.get("browser_path"))
        elif action == "sleep":
            res = cc.sleep(p["seconds"])
        elif action == "get_screen_size":
            res = cc.get_screen_size()
        elif action == "kill_process":
            res = cc.kill_process(p["name"])
        else:
            return SimpleSwarmResponse(success=False, message=f"Unknown action: {action}")

        return SimpleSwarmResponse(success=res.get("success", False), message=str(res.get("error", "OK")), data=res)

    except Exception as e:
        return SimpleSwarmResponse(success=False, message=f"Action failed: {e}")


# ---------------------------------------------------------------------------
# Screenshot endpoint
# ---------------------------------------------------------------------------

@router.get("/screenshot")
async def get_screenshot():
    """Capture desktop and return as base64 PNG."""
    from core.simpleswarm.computer_controller import ComputerController
    cc = ComputerController()
    res = cc.screenshot(save=False)
    if not res.get("success"):
        raise HTTPException(status_code=503, detail=res.get("error", "Screenshot failed"))
    return {
        "success": True,
        "image_base64": res["image_base64"],
        "width": res["width"],
        "height": res["height"],
    }


# ---------------------------------------------------------------------------
# Agent spawn endpoint
# ---------------------------------------------------------------------------

@router.post("/agents/spawn")
async def spawn_agents(req: SpawnAgentsRequest):
    """Spawn N SimpleSwarm test agents via the existing MassAgentOrchestrator."""
    from ..dependencies import get_swarm_orchestrator

    orch = get_swarm_orchestrator()
    spawned = []

    for i in range(req.count):
        agent_id = f"simpleswarm-{req.mode}-{int(time.time())}-{i}"
        try:
            # Submit a task to the existing orchestrator
            payload = {"mode": req.mode, "agent_id": agent_id}
            if hasattr(orch, "submit_task"):
                orch.submit_task(payload)
            elif hasattr(orch, "_orch") and hasattr(orch._orch, "submit_task"):
                orch._orch.submit_task(payload)
            spawned.append(agent_id)
        except Exception as e:
            return {"success": False, "message": f"Failed to spawn agent {i}: {e}", "spawned": spawned}

    return {"success": True, "message": f"Spawned {len(spawned)} agents", "spawned": spawned}


# ---------------------------------------------------------------------------
# Node info endpoints (for remote mesh discovery)
# ---------------------------------------------------------------------------

@router.get("/nodes/models")
async def list_local_models():
    """Return the Ollama models available on this node."""
    try:
        import urllib.request, json
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            models = [m.get("name", "") for m in data.get("models", [])]
            return {"models": models, "count": len(models)}
    except Exception as e:
        return {"models": [], "count": 0, "error": str(e)}


@router.get("/nodes/metrics")
async def local_metrics():
    """Return basic compute metrics for this node."""
    import psutil, platform
    try:
        mem = psutil.virtual_memory()
        return {
            "hostname": platform.node(),
            "cpu_percent": psutil.cpu_percent(interval=0.5),
            "memory_total_gb": round(mem.total / (1024**3), 1),
            "memory_available_gb": round(mem.available / (1024**3), 1),
            "gpu": "unknown",  # Could use nvidia-smi or similar
        }
    except Exception as e:
        return {"error": str(e)}
