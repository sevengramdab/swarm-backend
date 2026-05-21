#!/usr/bin/env python3
"""
llm_worker.py
=============
Worker function for MassAgentOrchestrator that calls a real LLM
via Ollama's local HTTP API.

ELI5: Instead of the agents just playing pretend, they now pick up
      a real telephone and call the brain (Ollama) to get an answer.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any, Dict, List, Optional

from core.mass_agent_swarm import Task

logger = logging.getLogger("LLMWorker")

OLLAMA_HOST = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2"

# Models known to fit on 8GB VRAM (GTX 1070 class)
SMALL_MODELS = ["llama3.2", "dolphin-llama3"]


def _get_available_models() -> List[str]:
    """Query Ollama for available models."""
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return [DEFAULT_MODEL]


def _pick_safe_model(preferred: str) -> str:
    """If the preferred model is likely too big, fall back to a small one."""
    available = _get_available_models()
    # Normalize: try exact match, then with :latest suffix, then without
    candidates = [preferred]
    if ':' not in preferred:
        candidates.append(preferred + ':latest')
    else:
        candidates.append(preferred.split(':')[0])
    for cand in candidates:
        if cand in available:
            preferred = cand
            break
    if preferred in available:
        if preferred.split(':')[0] not in SMALL_MODELS:
            logger.warning(f"Model {preferred} may be too large for 8GB VRAM; consider using {SMALL_MODELS}")
        return preferred
    # Fallback to default
    for cand in [DEFAULT_MODEL, DEFAULT_MODEL + ':latest']:
        if cand in available:
            return cand
    if available:
        # Prefer small models if available
        for small in SMALL_MODELS:
            for avail in available:
                if avail.startswith(small):
                    return avail
        return available[0]
    return DEFAULT_MODEL

MODE_PROMPTS = {
    "agent": "You are a helpful, concise AI assistant. Answer directly and clearly.",
    "plan": "You are a planning assistant. Break down the user's request into clear, numbered steps. Think through the approach before answering.",
    "research": "You are a research assistant. Investigate thoroughly, cite relevant facts, and provide comprehensive, well-structured answers with sources when possible.",
    "swarm_code": "You are an expert software engineer. Write clean, well-commented, production-ready code. Include explanations of key design decisions.",
    "debug": "You are a debugging expert. Analyze the user's problem systematically. Identify root causes, suggest fixes, and explain why the bug occurs.",
    "auto": "You are a versatile AI assistant. Adapt your response style to best fit the user's request.",
}


def llm_worker_fn(task: Task) -> Dict[str, Any]:
    """
    Process a task by calling the local Ollama API.
    Supports both single-prompt and conversation (messages) modes.
    """
    payload = task.payload or {}
    prompt = payload.get("prompt", "")
    raw_model = _strip_prefix(payload.get("model", DEFAULT_MODEL))
    model = _pick_safe_model(raw_model)
    system_prompt = payload.get("system_prompt")
    temperature = payload.get("temperature", 0.7)
    tier = payload.get("tier", "local")
    node_id = payload.get("node_id", "local")
    messages = payload.get("messages", [])
    mode = payload.get("mode", "agent")
    agent_config = payload.get("agent_config", {})  # per-agent overrides
    if agent_config.get("model"):
        model = _pick_safe_model(_strip_prefix(agent_config["model"]))
    if agent_config.get("temperature") is not None:
        temperature = float(agent_config["temperature"])

    if not prompt and not messages:
        return {"error": "No prompt provided", "task_id": task.id}

    # Build mode-specific system prompt if none provided
    if not system_prompt and mode in MODE_PROMPTS:
        system_prompt = MODE_PROMPTS[mode]

    logger.info(f"Agent processing task {task.id} | model={model} | mode={mode} | tier={tier}")

    try:
        response_text = _call_ollama_chat(
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            messages=messages,
        )
        return {
            "task_id": task.id,
            "model": model,
            "tier": tier,
            "node_id": node_id,
            "prompt": prompt,
            "response": response_text,
            "status": "completed",
            "mode": mode,
        }
    except Exception as exc:
        logger.error(f"LLM call failed for task {task.id}: {exc}")
        return {
            "task_id": task.id,
            "model": model,
            "tier": tier,
            "node_id": node_id,
            "prompt": prompt,
            "error": str(exc),
            "status": "failed",
            "mode": mode,
        }


def _strip_prefix(model_name: str) -> str:
    """Remove 'ollama/' prefix if present."""
    if model_name.startswith("ollama/"):
        return model_name[7:]
    return model_name


def _call_ollama_chat(
    prompt: str,
    model: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    messages: Optional[List[Dict[str, str]]] = None,
    timeout: float = 300.0,
) -> str:
    """Call Ollama /api/chat with conversation history support."""
    url = f"{OLLAMA_HOST}/api/chat"

    # Build messages array
    chat_messages: List[Dict[str, str]] = []

    if system_prompt:
        chat_messages.append({"role": "system", "content": system_prompt})

    # Add conversation history if provided
    if messages:
        for msg in messages:
            if isinstance(msg, dict):
                chat_messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
            else:
                # Handle pydantic model or other object
                chat_messages.append({"role": getattr(msg, "role", "user"), "content": getattr(msg, "content", "")})

    # Add current prompt if not already in messages
    if not messages or prompt:
        chat_messages.append({"role": "user", "content": prompt})

    body: Dict[str, Any] = {
        "model": model,
        "messages": chat_messages,
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }

    data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("message", {}).get("content", "")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error(f"Ollama HTTP {e.code}: {body}")
        # Try to parse Ollama error
        try:
            err_json = json.loads(body)
            err_msg = err_json.get("error", body)
        except Exception:
            err_msg = body or str(e)
        if "model requires more system memory" in err_msg.lower():
            raise RuntimeError(
                f"Model '{model}' is too large for your GPU/system memory. "
                f"Try a smaller model like llama3.2 or dolphin-llama3."
            ) from e
        raise RuntimeError(f"Ollama error ({e.code}): {err_msg}") from e
