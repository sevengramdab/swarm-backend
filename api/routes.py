"""FastAPI routes for the swarm backend."""

import json
from typing import Optional
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.config import settings, APIMode
from core.model_router import discover_local_models, discover_cloud_models, select_model
from modes.ask_mode import ask
from modes.plan_mode import plan, execute_step
from modes.agent_mode import agent_run
from modes.swarm_mode import swarm_run

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
    return {"status": "ok", "api_mode": settings.api_mode.value}


@router.get("/models")
async def list_models():
    """List all available models based on current API mode."""
    local = await discover_local_models()
    cloud = await discover_cloud_models()
    
    if settings.api_mode == APIMode.LOCAL_ONLY:
        return {"models": local, "mode": settings.api_mode.value}
    elif settings.api_mode == APIMode.CLOUD_ONLY:
        return {"models": cloud, "mode": settings.api_mode.value}
    else:
        return {"models": local + cloud, "mode": settings.api_mode.value, "local": local, "cloud": cloud}


@router.get("/settings")
async def get_settings():
    return {
        "api_mode": settings.api_mode.value,
        "local_model": settings.local_model,
        "cloud_model": settings.cloud_model,
        "ollama_url": settings.ollama_url,
        "lm_studio_url": settings.lm_studio_url,
    }


@router.post("/settings")
async def update_settings(update: SettingsUpdate):
    if update.api_mode:
        settings.api_mode = APIMode(update.api_mode)
    if update.local_model:
        settings.local_model = update.local_model
    if update.cloud_model:
        settings.cloud_model = update.cloud_model
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
