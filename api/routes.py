"""FastAPI routes for the swarm backend."""

import json
import os
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core import config as cfg
from core.autonomy_engine import AutonomyLevel, SSEEvent
from core.session_store import store
from core.change_tracker import tracker, ChangeBatch, ChangeStatus, BatchStatus
from core.model_router import discover_local_models, discover_cloud_models, select_model
from core.swarm_state import state_manager
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
    workspace_path: Optional[str] = None  # Absolute workspace root for tool execution
    documents: Optional[list] = None  # List of document strings for RAG grounding
    document_names: Optional[list] = None  # Optional labels for each document
    auto_execute: bool = False
    autonomy_level: str = "default"  # default | override | autopilot
    batch_mode: bool = True  # track changes for batch review
    temperature: Optional[float] = None  # LLM temperature (0-1)
    model: Optional[str] = None  # explicit model selection
    orchestrator_model: Optional[str] = None  # orchestrator LLM for swarm
    subagent_mode: Optional[str] = None  # cloud | local | hybrid
    session_id: Optional[str] = None  # optional session ID for dashboard sync


class SettingsUpdate(BaseModel):
    api_mode: Optional[str] = None
    local_model: Optional[str] = None
    cloud_model: Optional[str] = None
    temperature: Optional[float] = None
    orchestrator_model: Optional[str] = None
    subagent_mode: Optional[str] = None


class ApprovalResponse(BaseModel):
    session_id: str
    request_id: str
    approved: bool


class ToolResultPayload(BaseModel):
    session_id: str
    request_id: str
    tool: str
    args: dict
    status: str
    data: Optional[dict] = None
    error: Optional[str] = ""


class DecisionResponse(BaseModel):
    session_id: str
    request_id: str
    decision: str


class CompactRequest(BaseModel):
    session_id: str
    summary: str = ""


class SteerRequest(BaseModel):
    message: str


class AgentSteerRequest(BaseModel):
    message: str


class AgentCreateRequest(BaseModel):
    parent_id: str
    role: str
    name: str
    system_prompt: str = ""


@router.get("/health")
async def health():
    return {"status": "ok", "api_mode": cfg.API_MODE}


@router.get("/health/ollama")
async def health_ollama():
    """Proxy Ollama health check to avoid CORS issues from file:// dashboards."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://127.0.0.1:11434/api/tags")
            return {"ok": resp.status_code == 200, "status_code": resp.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/models")
async def list_models():
    """List all available models based on current API mode."""
    local = await discover_local_models()
    cloud = await discover_cloud_models()
    
    if cfg.API_MODE == "local_only":
        return {"models": local, "mode": cfg.API_MODE}
    elif cfg.API_MODE == "cloud_only":
        return {"models": cloud, "mode": cfg.API_MODE}
    else:
        return {"models": local + cloud, "mode": cfg.API_MODE, "local": local, "cloud": cloud}


@router.get("/settings")
async def get_settings():
    return {
        "api_mode": cfg.API_MODE,
        "local_model": cfg.LOCAL_MODEL,
        "cloud_model": cfg.CLOUD_MODEL,
        "orchestrator_model": cfg.ORCHESTRATOR_MODEL,
        "subagent_mode": cfg.SUBAGENT_MODE,
        "ollama_url": cfg.OLLAMA_URL,
        "lm_studio_url": cfg.LMSTUDIO_URL,
        "temperature": cfg.TEMPERATURE,
    }


@router.post("/settings")
async def update_settings(update: SettingsUpdate):
    if update.api_mode:
        cfg.API_MODE = update.api_mode
    if update.local_model:
        cfg.LOCAL_MODEL = update.local_model
    if update.cloud_model:
        cfg.CLOUD_MODEL = update.cloud_model
    if update.orchestrator_model:
        cfg.ORCHESTRATOR_MODEL = update.orchestrator_model
    if update.subagent_mode:
        cfg.SUBAGENT_MODE = update.subagent_mode
    if update.temperature is not None:
        cfg.TEMPERATURE = max(0.0, min(1.0, update.temperature))
    return {"ok": True, "settings": await get_settings()}


@router.get("/workspace")
async def get_workspace():
    """Return the current workspace root directory."""
    return {"workspace_root": cfg.WORKSPACE_ROOT}


class WorkspaceUpdate(BaseModel):
    workspace_root: str


@router.post("/workspace")
async def update_workspace(update: WorkspaceUpdate):
    """Set the workspace root directory for tool execution."""
    import os
    path = update.workspace_root
    if path and os.path.isdir(path):
        cfg.WORKSPACE_ROOT = path
        return {"ok": True, "workspace_root": cfg.WORKSPACE_ROOT}
    elif path:
        # Try to create it
        try:
            os.makedirs(path, exist_ok=True)
            cfg.WORKSPACE_ROOT = path
            return {"ok": True, "workspace_root": cfg.WORKSPACE_ROOT}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Cannot create directory: {e}")
    else:
        raise HTTPException(status_code=400, detail="workspace_root is required")


class VSCodeOpenRequest(BaseModel):
    path: Optional[str] = None  # file or folder to open; defaults to workspace root


@router.post("/vscode/open")
async def open_vscode(req: VSCodeOpenRequest):
    """Open a file or folder in VS Code: (spawns process to avoid browser protocol issues)."""
    import os
    import subprocess
    import platform

    target = req.path or cfg.WORKSPACE_ROOT
    if not target or not os.path.exists(target):
        raise HTTPException(status_code=404, detail="Path does not exist")

    workspace_root = cfg.WORKSPACE_ROOT

    # Just open the folder directly — .code-workspace files can cause extension/env issues
    # Keep target as the folder path (or file path if a specific file was requested)

    # Find VS Code: executable
    system = platform.system()
    candidates = []
    if system == "Windows":
        candidates = ["code.cmd", "code"]
        # Common Windows install paths
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("ProgramFiles", "")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", "")
        if local_appdata:
            candidates.append(os.path.join(local_appdata, "Programs", "Microsoft VS Code:", "bin", "code.cmd"))
        if program_files:
            candidates.append(os.path.join(program_files, "Microsoft VS Code:", "bin", "code.cmd"))
        if program_files_x86:
            candidates.append(os.path.join(program_files_x86, "Microsoft VS Code:", "bin", "code.cmd"))
    else:
        candidates = ["code"]

    vscode_path = None
    for c in candidates:
        try:
            result = subprocess.run([c, "--version"], capture_output=True, timeout=5)
            if result.returncode == 0:
                vscode_path = c
                break
        except Exception:
            continue

    if not vscode_path:
        raise HTTPException(status_code=500, detail="VS Code: not found. Is it installed and in PATH?")

    try:
        subprocess.Popen([vscode_path, target], shell=False)
        return {"ok": True, "path": target, "vscode": vscode_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open VS Code: {e}")


async def _stream_structured(generator):
    """Helper to stream structured SSE events."""
    yield f"data: {json.dumps({'type': 'status', 'message': 'Thinking...'})}\n\n"
    async for event in generator:
        if isinstance(event, SSEEvent):
            yield f"data: {event.to_json()}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'text', 'chunk': str(event)})}\n\n"
    yield f"data: {json.dumps({'type': 'done'})}\n\n"


@router.post("/chat")
async def chat(req: ChatRequest):
    """Main chat endpoint — routes to the correct mode with autonomy level."""
    mode = req.mode.lower()
    autonomy = req.autonomy_level.lower()
    if autonomy not in ("default", "override", "autopilot"):
        autonomy = "default"

    # Update workspace root for tool execution if provided
    if req.workspace_path:
        cfg.WORKSPACE_ROOT = req.workspace_path

    if mode == "ask":
        gen = ask(
            question=req.message,
            history=req.history or [],
            workspace_context=req.workspace_context,
            documents=req.documents or [],
            document_names=req.document_names or [],
            stream=True,
            temperature=req.temperature,
            model=req.model,
        )
        return StreamingResponse(_stream_structured(gen), media_type="text/event-stream")
    elif mode == "plan":
        gen = plan(
            request=req.message,
            workspace_context=req.workspace_context,
            auto_execute=req.auto_execute,
            stream=True,
            temperature=req.temperature,
            model=req.model,
        )
        return StreamingResponse(_stream_structured(gen), media_type="text/event-stream")
    elif mode == "agent":
        gen = agent_run(
            task=req.message,
            workspace_context=req.workspace_context,
            stream=True,
            autonomy_level=autonomy,
            batch_mode=req.batch_mode,
            temperature=req.temperature,
            model=req.model,
        )
        return StreamingResponse(_stream_structured(gen), media_type="text/event-stream")
    elif mode == "swarm":
        gen = swarm_run(
            task=req.message,
            workspace_context=req.workspace_context,
            autonomy_level=autonomy,
            batch_mode=req.batch_mode,
            temperature=req.temperature,
            model=req.model,
            orchestrator_model=req.orchestrator_model,
            subagent_mode=req.subagent_mode,
            session_id=req.session_id,
        )
        return StreamingResponse(_stream_structured(gen), media_type="text/event-stream")
    else:
        async def error_gen():
            yield SSEEvent("error", {"message": f"Unknown mode: {mode}"})
        gen = error_gen()
        return StreamingResponse(_stream_structured(gen), media_type="text/event-stream")


@router.post("/approval/respond")
async def approval_respond(resp: ApprovalResponse):
    """User responds to an approval request."""
    ok = store.set_approval(resp.session_id, resp.request_id, resp.approved)
    return {"ok": ok, "session_id": resp.session_id, "request_id": resp.request_id}


@router.post("/decision/respond")
async def decision_respond(resp: DecisionResponse):
    """User responds to a decision gate (OVERRIDE mode ambiguity)."""
    ok = store.set_decision(resp.session_id, resp.request_id, resp.decision)
    return {"ok": ok, "session_id": resp.session_id, "request_id": resp.request_id}


@router.post("/agent/tool-result")
async def agent_tool_result(payload: ToolResultPayload):
    """Receive tool execution results from the VS Code: extension."""
    from core.autonomy_engine import ToolResult
    result = ToolResult(
        tool=payload.tool,
        args=payload.args,
        status=payload.status,
        data=payload.data,
        error=payload.error or "",
    )
    ok = store.set_tool_result(payload.session_id, payload.request_id, result)
    return {"ok": ok, "session_id": payload.session_id, "request_id": payload.request_id}


@router.get("/workspace/summary")
async def workspace_summary(path: str = Query(...)):
    """Generate a summary of the workspace — delegated to extension."""
    return {"path": path, "summary": "Workspace summary placeholder"}


@router.post("/compact")
async def compact_session(req: CompactRequest):
    """Compact a swarm session to free up context/memory."""
    result = store.compact(req.session_id, req.summary)
    return result


@router.post("/sessions/{session_id}/stop")
async def stop_session(session_id: str):
    """Signal a running session to stop."""
    ok = store.stop(session_id)
    if not ok:
        return {"ok": False, "error": "Session not found"}
    return {"ok": True, "session_id": session_id, "status": "stopped"}


@router.post("/sessions/{session_id}/save")
async def save_session(session_id: str):
    """Save a session's chat history to disk."""
    return store.save(session_id)


@router.post("/sessions/{session_id}/load")
async def load_session(session_id: str):
    """Load a previously saved session."""
    return store.load(session_id)


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session from memory and disk."""
    return store.delete_saved(session_id)


@router.get("/sessions")
async def list_sessions():
    """List all saved sessions on disk."""
    return {"sessions": store.list_saved()}


@router.post("/sessions/{session_id}/steer")
async def steer_session(session_id: str, req: SteerRequest):
    """Inject a steering message into a running session."""
    ok = store.push_steering(session_id, req.message)
    if not ok:
        return {"ok": False, "error": "Session not found"}
    return {"ok": True, "session_id": session_id, "message": req.message}


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


# ───────────────────────────────────────────────
# Command Viewport Dashboard Endpoints
# ───────────────────────────────────────────────

@router.websocket("/ws/dashboard/{session_id}")
async def dashboard_ws(websocket: WebSocket, session_id: str):
    """WebSocket for real-time Command Viewport dashboard updates."""
    await websocket.accept()
    await state_manager.subscribe_ws(session_id, websocket)
    try:
        while True:
            # Keep connection alive, handle incoming steer messages from dashboard
            data = await websocket.receive_json()
            if data.get("action") == "steer" and data.get("agent_id"):
                agent_id = data["agent_id"]
                message = data.get("message", "")
                store.push_steering(session_id, f"[Agent {agent_id}] {message}")
                await state_manager.broadcast(session_id, {
                    "type": "steer_ack",
                    "agent_id": agent_id,
                    "message": message,
                })
            elif data.get("action") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await state_manager.unsubscribe_ws(session_id, websocket)
    except Exception:
        await state_manager.unsubscribe_ws(session_id, websocket)


@router.get("/swarms/{session_id}/tree")
async def get_swarm_tree(session_id: str):
    """Get the recursive agent tree for a session."""
    tree = state_manager.get_tree(session_id)
    if tree is None:
        raise HTTPException(status_code=404, detail="Swarm not found")
    return {"tree": tree}


@router.get("/swarms/{session_id}/circuit")
async def get_circuit_status(session_id: str):
    """Get aggregate circuit status for a session."""
    circuit = state_manager.get_circuit_status(session_id)
    return circuit


@router.get("/agents/{agent_id}/detail")
async def get_agent_detail(agent_id: str):
    """Get full agent detail including thoughts and telemetry."""
    detail = state_manager.get_agent_detail(agent_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return detail


@router.post("/agents/{agent_id}/steer")
async def steer_agent(agent_id: str, req: AgentSteerRequest):
    """Send a steering message targeting a specific agent."""
    agent = state_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    store.push_steering(agent.session_id, f"[Steer @{agent.name}] {req.message}")
    await state_manager.broadcast_agent_update(agent.session_id, agent_id)
    return {"ok": True, "agent_id": agent_id, "message": req.message}


@router.post("/agents/{agent_id}/tasks")
async def create_agent_task(agent_id: str, req: AgentCreateRequest):
    """Create a new task for an agent (used by dashboard or orchestrator)."""
    agent = state_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    task = state_manager.add_task(agent_id, req.name)
    if task:
        await state_manager.broadcast_task_update(agent.session_id, agent_id, task)
    return {"ok": True, "task": task.to_dict() if task else None}


@router.get("/swarms/{session_id}/telemetry")
async def get_session_telemetry(session_id: str):
    """Get aggregate telemetry for all agents in a session."""
    agents = state_manager.get_session_agents(session_id)
    return {
        "agents": [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "role": a.role,
                "telemetry": a.telemetry.to_dict(),
            }
            for a in agents
        ]
    }


# ───────────────────────────────────────────────
# Change Batch Review Endpoints
# ───────────────────────────────────────────────

class BatchActionRequest(BaseModel):
    batch_id: str
    change_id: Optional[str] = None
    all: bool = False


class BatchApplyRequest(BaseModel):
    batch_id: str


class BatchUndoRequest(BaseModel):
    batch_id: str


@router.get("/sessions/{session_id}/batches")
async def list_batches(session_id: str):
    """List all change batches for a session."""
    batches = tracker.get_batches_for_session(session_id)
    return {"batches": [b.to_dict() for b in batches]}


@router.get("/batches/{batch_id}")
async def get_batch(batch_id: str):
    """Get a single change batch with full diff data."""
    batch = tracker.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch.to_dict()


@router.post("/batches/{batch_id}/approve")
async def approve_batch(batch_id: str, req: BatchActionRequest):
    """Approve one change (change_id) or all pending changes in a batch."""
    batch = tracker.get_batch(batch_id)
    if not batch:
        return {"ok": False, "error": "Batch not found"}
    target = req.change_id if req.change_id else (None if req.all else None)
    updated = batch.approve(target)
    return {"ok": True, "batch_id": batch_id, "updated": updated, "stats": batch.stats()}


@router.post("/batches/{batch_id}/reject")
async def reject_batch(batch_id: str, req: BatchActionRequest):
    """Reject one change (change_id) or all pending changes in a batch."""
    batch = tracker.get_batch(batch_id)
    if not batch:
        return {"ok": False, "error": "Batch not found"}
    target = req.change_id if req.change_id else (None if req.all else None)
    updated = batch.reject(target)
    return {"ok": True, "batch_id": batch_id, "updated": updated, "stats": batch.stats()}


@router.post("/batches/{batch_id}/apply")
async def apply_batch(batch_id: str, req: BatchApplyRequest):
    """Mark a batch as applied (the extension actually writes files)."""
    batch = tracker.get_batch(batch_id)
    if not batch:
        return {"ok": False, "error": "Batch not found"}
    batch.mark_applied()
    return {"ok": True, "batch_id": batch_id, "stats": batch.stats()}


@router.post("/batches/{batch_id}/undo")
async def undo_batch(batch_id: str, req: BatchUndoRequest):
    """Mark a batch as undone (the extension reverts files)."""
    batch = tracker.get_batch(batch_id)
    if not batch:
        return {"ok": False, "error": "Batch not found"}
    batch.mark_undone()
    return {"ok": True, "batch_id": batch_id, "stats": batch.stats()}


@router.get("/batches/{batch_id}/changes/{change_id}")
async def get_batch_change(batch_id: str, change_id: str):
    """Get a single change from a batch."""
    batch = tracker.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    for change in batch.changes:
        if change.change_id == change_id:
            return change.to_dict()
    raise HTTPException(status_code=404, detail="Change not found")


@router.post("/batches/{batch_id}/status")
async def set_batch_status(batch_id: str, status: str):
    """Set batch status (open, reviewing, applying, etc.)."""
    batch = tracker.get_batch(batch_id)
    if not batch:
        return {"ok": False, "error": "Batch not found"}
    try:
        batch.status = BatchStatus(status)
    except ValueError:
        return {"ok": False, "error": f"Invalid status: {status}"}
    return {"ok": True, "batch_id": batch_id, "status": batch.status.value}


# ═══════════════════════════════════════════════════════
# Etsy Dropshipping Tool Suite
# ═══════════════════════════════════════════════════════

import re


def _repair_json(text: str) -> str:
    """Fix common LLM JSON issues: unescaped newlines inside string values."""
    # Find the outermost JSON object/array
    json_start = text.find("{")
    json_end = text.rfind("}")
    if json_start < 0 or json_end <= json_start:
        json_start = text.find("[")
        json_end = text.rfind("]")
    if json_start >= 0 and json_end > json_start:
        text = text[json_start:json_end + 1]

    # Replace literal newlines inside JSON string values with \n
    result = []
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            result.append(ch)
            escape_next = False
            continue
        if ch == "\\":
            result.append(ch)
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string and ch == "\n":
            result.append("\\n")
            continue
        if in_string and ch == "\t":
            result.append("\\t")
            continue
        result.append(ch)
    return "".join(result)


def _parse_llm_json(text: str):
    """Try to parse JSON from LLM output, with repair fallback."""
    repaired = _repair_json(text)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        return None

class EtsyListingRequest(BaseModel):
    product_name: str
    category: str = ""
    style: str = ""
    keywords: str = ""
    tone: str = "professional"
    model: Optional[str] = None


class EtsyKeywordsRequest(BaseModel):
    niche: str
    count: int = 13
    model: Optional[str] = None


class EtsyCompetitorsRequest(BaseModel):
    keyword: str
    max_results: int = 5


class EtsyPricingRequest(BaseModel):
    product_cost: float
    shipping_cost: float = 0
    target_margin: float = 40
    competitor_low: float = 0
    competitor_high: float = 0


class EtsyVaultSaveRequest(BaseModel):
    name: str
    title: str = ""
    description: str = ""
    tags: list = []
    price: float = 0
    cost: float = 0
    notes: str = ""


VAULT_FILE = os.path.join(os.path.dirname(__file__), "..", "etsy_vault.json")


def _load_vault() -> list:
    try:
        if os.path.exists(VAULT_FILE):
            with open(VAULT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_vault(vault: list):
    try:
        os.makedirs(os.path.dirname(VAULT_FILE), exist_ok=True)
        with open(VAULT_FILE, "w", encoding="utf-8") as f:
            json.dump(vault, f, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save vault: {e}")


@router.post("/tools/etsy/listing")
async def generate_etsy_listing(req: EtsyListingRequest):
    """Generate a complete Etsy listing (title, description, tags) using LLM."""
    from core.model_router import chat_completion
    prompt = f"""You are an expert Etsy SEO copywriter with 10+ years of experience. Generate a complete, high-converting Etsy listing.

Product: {req.product_name}
Category: {req.category or 'General Handmade'}
Style/Vibe: {req.style or 'Modern'}
Tone: {req.tone}
Additional keywords to include: {req.keywords or 'none'}

Requirements:
- Title must be under 140 characters and packed with high-value keywords
- Description should be 4-6 paragraphs, HTML-formatted with <p> tags, emotional and persuasive
- Include care instructions, shipping info placeholder, and personalization call-to-action
- Tags must be exactly 13 tags, each under 20 characters, highly relevant
- Suggest a competitive price based on typical handmade margins

Return ONLY a valid JSON object with this exact structure (no markdown, no explanation):
{{
  "title": "...",
  "description": "<p>...</p><p>...</p>",
  "tags": ["tag1", "tag2", ...],
  "attributes": {{"occasion": "...", "material": "..."}},
  "price_suggestion": 29.99,
  "seo_notes": "brief explanation of keyword choices"
}}"""
    messages = [{"role": "user", "content": prompt}]
    result = ""
    async for chunk in chat_completion(messages, model=req.model, stream=False, temperature=0.8):
        result += chunk

    # Extract JSON from response
    data = _parse_llm_json(result)
    if data:
        return {"ok": True, "listing": data}
    # Fallback: return raw text
    return {"ok": True, "listing_raw": result, "note": "Could not parse JSON, returned raw"}


@router.post("/tools/etsy/keywords")
async def generate_etsy_keywords(req: EtsyKeywordsRequest):
    """Generate SEO-optimized Etsy tags/keywords for a niche."""
    from core.model_router import chat_completion
    prompt = f"""You are an Etsy SEO expert. Generate {req.count} high-performing Etsy tags for this niche.

Niche: {req.niche}

Rules:
- Each tag must be under 20 characters (Etsy's limit)
- Mix of broad and long-tail keywords
- Include seasonal/gifting keywords where relevant
- Tags should be what buyers actually type in search

Return ONLY a JSON array of strings (no markdown, no explanation):
["tag1", "tag2", ...]"""
    messages = [{"role": "user", "content": prompt}]
    result = ""
    async for chunk in chat_completion(messages, model=req.model, stream=False, temperature=0.7):
        result += chunk

    data = _parse_llm_json(result)
    if data and isinstance(data, list):
        return {"ok": True, "niche": req.niche, "keywords": data}
    # Fallback: split by lines
    lines = [l.strip("-\"' ") for l in result.split("\n") if l.strip() and not l.strip().startswith("[") and not l.strip().startswith("]")]
    return {"ok": True, "niche": req.niche, "keywords": lines[:req.count], "note": "Parsed from raw text"}


@router.post("/tools/etsy/competitors")
async def research_etsy_competitors(req: EtsyCompetitorsRequest):
    """Research Etsy competitors for a keyword using web search."""
    from core.tool_executor import _web_search
    search_query = f"site:etsy.com {req.keyword}"
    results = _web_search(search_query, req.max_results)
    return {"ok": results.get("status") == "ok", "keyword": req.keyword, **results}


@router.post("/tools/etsy/pricing")
async def optimize_etsy_pricing(req: EtsyPricingRequest):
    """Calculate optimal Etsy pricing with fee breakdown."""
    from core.tool_executor import execute_tool
    result = execute_tool("etsy_pricing_optimizer", {
        "product_cost": req.product_cost,
        "shipping_cost": req.shipping_cost,
        "target_margin": req.target_margin,
        "competitor_low": req.competitor_low,
        "competitor_high": req.competitor_high,
    })
    return {"ok": result.get("status") == "ok", **result}


@router.post("/tools/etsy/vault/save")
async def save_to_vault(req: EtsyVaultSaveRequest):
    """Save a product listing to the local product vault."""
    vault = _load_vault()
    entry = {
        "id": f"vault-{len(vault) + 1:03d}",
        "name": req.name,
        "title": req.title,
        "description": req.description,
        "tags": req.tags,
        "price": req.price,
        "cost": req.cost,
        "notes": req.notes,
        "created": int(__import__('time').time()),
    }
    vault.insert(0, entry)
    _save_vault(vault)
    return {"ok": True, "entry": entry}


@router.get("/tools/etsy/vault/list")
async def list_vault():
    """List all saved products in the vault."""
    vault = _load_vault()
    return {"ok": True, "count": len(vault), "entries": vault}


@router.get("/tools/etsy/vault/{entry_id}")
async def get_vault_entry(entry_id: str):
    """Get a specific vault entry."""
    vault = _load_vault()
    for entry in vault:
        if entry.get("id") == entry_id:
            return {"ok": True, "entry": entry}
    raise HTTPException(status_code=404, detail="Vault entry not found")


@router.delete("/tools/etsy/vault/{entry_id}")
async def delete_vault_entry(entry_id: str):
    """Delete a vault entry."""
    vault = _load_vault()
    new_vault = [e for e in vault if e.get("id") != entry_id]
    if len(new_vault) == len(vault):
        raise HTTPException(status_code=404, detail="Vault entry not found")
    _save_vault(new_vault)
    return {"ok": True, "deleted_id": entry_id}


# Legacy compatibility endpoints for OrbitScribe HTML
@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """Streaming chat — alias for /chat."""
    return await chat(req)


@router.post("/swarm")
async def swarm(req: ChatRequest):
    """Alias for /chat — defaults to ask mode."""
    req.mode = "ask"
    return await chat(req)


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
