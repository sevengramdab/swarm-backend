"""
OrbitScribe Swarm Backend
FastAPI service for multi-agent LLM orchestration.
"""
import os
import asyncio
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents.swarm_orchestrator import orchestrator
from core.model_router import router

app = FastAPI(title="OrbitScribe Swarm", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:*", "vscode-webview://*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request models
class ChatRequest(BaseModel):
    message: str
    mode: str = "ask"  # ask | plan | agent | swarm
    agent: Optional[str] = None
    workspace_context: Optional[str] = ""

class HealthResponse(BaseModel):
    status: str
    api_mode: str
    version: str

@app.get("/api/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        api_mode=router.mode,
        version="1.0.0"
    )

@app.get("/api/mode")
async def get_mode():
    return {"mode": router.mode}

@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Non-streaming chat for simple queries."""
    messages = [
        {"role": "system", "content": f"You are OrbitScribe, an AI coding assistant. Mode: {req.mode}. Be concise and helpful."},
        {"role": "user", "content": f"Context: {req.workspace_context}\n\n{req.message}"}
    ]
    response = await router.chat(messages, mode=req.mode)
    return {"response": response, "mode": req.mode}

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """Streaming chat with SSE-style response."""
    async def generate():
        messages = [
            {"role": "system", "content": f"You are OrbitScribe, an AI coding assistant. Mode: {req.mode}. Be concise and helpful."},
            {"role": "user", "content": f"Context: {req.workspace_context}\n\n{req.message}"}
        ]
        
        # Simulate streaming by getting full response then chunking
        # In production, use actual streaming LLM APIs
        full = await router.chat(messages, mode=req.mode)
        chunk_size = 8
        for i in range(0, len(full), chunk_size):
            chunk = full[i:i+chunk_size]
            yield f'data: {{"chunk": {repr(chunk)}}}\n\n'
            await asyncio.sleep(0.03)
        yield 'data: {"done": true}\n\n'

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.post("/api/swarm")
async def swarm(req: ChatRequest):
    """Run the multi-agent swarm on a task."""
    async def generate():
        async for result in orchestrator.run_swarm(req.message, req.workspace_context or ""):
            import json
            yield f'data: {json.dumps(result)}\n\n'
        yield 'data: {"done": true}\n\n'

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.post("/api/plan")
async def plan(req: ChatRequest):
    """Generate an implementation plan."""
    messages = [
        {"role": "system", "content": "You are a software architect. Create detailed implementation plans with file structure, dependencies, and step-by-step tasks."},
        {"role": "user", "content": f"Context: {req.workspace_context}\n\nPlan this: {req.message}"}
    ]
    response = await router.chat(messages, mode="plan")
    return {"plan": response}

@app.post("/api/agent")
async def agent_run(req: ChatRequest):
    """Run a specific agent."""
    if not req.agent:
        return {"error": "agent field required"}
    result = await orchestrator.run_single(req.agent, req.message, req.workspace_context or "")
    return {"agent": req.agent, "result": result}

@app.get("/api/agents")
async def list_agents():
    from agents.base import AGENT_REGISTRY
    return {
        key: {"name": a.name, "role": a.role}
        for key, a in AGENT_REGISTRY.items()
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("SWARM_PORT", 58081))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
