"""FastAPI routes for the swarm backend."""

import json
from typing import Optional
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core import config as cfg
from core.model_router import discover_local_models, discover_cloud_models, select_model
from modes.ask_mode import ask
from modes.plan_mode import plan, execute_step
from modes.agent_mode import agent_run
from modes.swarm_mode import swarm_run
from agents.swarm_orchestrator import orchestrator

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    mode: str = "ask"  # ask | plan | agent | swarm
    history: Optional[list] = None
    workspace_context: str = ""
    auto_execute: bool = False


class SettingsUpdate(BaseModel):
    api_mode: Optional[str] = None
    local_model: Optional[str] = None
    cloud_model: Optional[str] = None


@router.get("/health")
async def health():
    return {"status": "ok", "api_mode": cfg.API_MODE}


@router.get("/models")
async def list_models():
    """List all available models based on current API mode."""
    local = await discover_local_models()
    cloud = await discover_cloud_models()
    
    if cfg.API_MODE == "local-only":
        return {"models": local, "mode": cfg.API_MODE}
    elif cfg.API_MODE == "cloud-only":
        return {"models": cloud, "mode": cfg.API_MODE}
    else:
        return {"models": local + cloud, "mode": cfg.API_MODE, "local": local, "cloud": cloud}


@router.get("/settings")
async def get_settings():
    return {
        "api_mode": cfg.API_MODE,
        "local_model": cfg.LOCAL_MODEL,
        "cloud_model": cfg.CLOUD_MODEL,
        "ollama_url": cfg.OLLAMA_URL,
        "lm_studio_url": cfg.LMSTUDIO_URL,
    }


@router.post("/settings")
async def update_settings(update: SettingsUpdate):
    if update.api_mode:
        cfg.API_MODE = update.api_mode
    if update.local_model:
        cfg.LOCAL_MODEL = update.local_model
    if update.cloud_model:
        cfg.CLOUD_MODEL = update.cloud_model
    return {"ok": True, "settings": await get_settings()}


async def _stream_response(generator):
    """Helper to stream async generator as SSE."""
    async for chunk in generator:
        yield f"data: {json.dumps({'chunk': chunk})}\n\n"
    yield f"data: {json.dumps({'done': True})}\n\n"


@router.post("/chat")
async def chat(req: ChatRequest):
    """Main chat endpoint — routes to the correct mode."""
    mode = req.mode.lower()
    
    if mode == "ask":
        gen = ask(
            question=req.message,
            history=req.history or [],
            workspace_context=req.workspace_context,
            stream=True,
        )
    elif mode == "plan":
        gen = plan(
            request=req.message,
            workspace_context=req.workspace_context,
            auto_execute=req.auto_execute,
            stream=True,
        )
    elif mode == "agent":
        gen = agent_run(
            task=req.message,
            workspace_context=req.workspace_context,
            stream=True,
        )
    elif mode == "swarm":
        gen = swarm_run(
            task=req.message,
            workspace_context=req.workspace_context,
        )
    else:
        async def error_gen():
            yield json.dumps({"error": f"Unknown mode: {mode}"})
        gen = error_gen()
    
    return StreamingResponse(_stream_response(gen), media_type="text/event-stream")


@router.post("/agent/tool-result")
async def agent_tool_result(session_id: str, tool_result: dict):
    """Receive tool execution results from the VS Code extension."""
    # TODO: Implement session tracking and tool result injection
    return {"ok": True, "session_id": session_id}


@router.get("/workspace/summary")
async def workspace_summary(path: str = Query(...)):
    """Generate a summary of the workspace — delegated to extension."""
    # The extension calls this after scanning the workspace
    return {"path": path, "summary": "Workspace summary placeholder"}


@router.get("/agents")
async def list_agents():
    """List available specialized agents."""
    return {
        "code": {"name": "Code", "role": "Generate, refactor, and debug code"},
        "review": {"name": "Review", "role": "Review code for bugs, security, and style"},
        "test": {"name": "Test", "role": "Write tests and check coverage"},
        "doc": {"name": "Doc", "role": "Write documentation and READMEs"},
        "plan": {"name": "Plan", "role": "Architect and plan features"},
    }


# Legacy compatibility endpoints for OrbitScribe HTML
@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """Streaming chat — alias for /chat."""
    return await chat(req)


@router.post("/swarm")
async def swarm(req: ChatRequest):
    """Run the multi-agent swarm on a task — streams raw agent JSON."""
    async def generate():
        async for result in orchestrator.run_swarm(req.message, req.workspace_context or ""):
            yield f"data: {json.dumps(result)}\n\n"
        yield "data: {\"done\": true}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/plan")
async def plan_endpoint(req: ChatRequest):
    """Generate an implementation plan."""
    req.mode = "plan"
    return await chat(req)


@router.post("/agent")
async def agent_endpoint(req: ChatRequest):
    """Run a specific agent."""
    req.mode = "agent"
    return await chat(req)
