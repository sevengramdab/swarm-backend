"""LLM Integration — Ollama and LM Studio proxies."""
import json
import logging
import re
from typing import Any, AsyncGenerator, Dict, List

import httpx

from core import config

logger = logging.getLogger(__name__)

_http_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0))
    return _http_client


async def close_client() -> None:
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None


async def detect_ollama_models() -> List[Dict[str, Any]]:
    try:
        client = get_client()
        resp = await client.get(f"{config.OLLAMA_URL}/api/tags", timeout=2.0)
        if resp.status_code == 200:
            data = resp.json()
            return [
                {"name": m.get("name", m.get("model", "unknown")), "provider": "ollama"}
                for m in data.get("models", [])
            ]
    except Exception as e:
        logger.debug(f"Ollama not reachable: {e}")
    return []


async def detect_lmstudio_models() -> List[Dict[str, Any]]:
    try:
        client = get_client()
        resp = await client.get(f"{config.LMSTUDIO_URL}/v1/models", timeout=2.0)
        if resp.status_code == 200:
            data = resp.json()
            return [
                {"name": m.get("id", "unknown"), "provider": "lmstudio"}
                for m in data.get("data", [])
            ]
    except Exception as e:
        logger.debug(f"LM Studio not reachable: {e}")
    return []


async def _get_ollama_model(model: str | None = None) -> str:
    """Resolve model name, falling back to first available if not found."""
    model = model or config.LOCAL_MODEL
    client = get_client()
    try:
        resp = await client.post(f"{config.OLLAMA_URL}/api/generate", json={"model": model, "prompt": "hi", "stream": False}, timeout=5.0)
        if resp.status_code == 200:
            return model
    except Exception:
        pass
    # Model not found, pick first available (prefer smaller models by parameter count in name)
    models = await detect_ollama_models()
    if models:
        # Sort by estimated parameter size (1.5b < 3b < 7b < 8b < 14b < etc.)
        def _size_key(m):
            name = m["name"].lower()
            match = re.search(r":(\d+(?:\.\d+)?)b", name)
            if match:
                return float(match.group(1))
            return 999
        models.sort(key=_size_key)
        return models[0]["name"]
    return model  # fallback, will likely error


def _messages_to_prompt(messages: List[Dict[str, str]]) -> str:
    """Convert chat messages to a single prompt for /api/generate."""
    parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            parts.append(f"[System]: {content}")
        elif role == "user":
            parts.append(f"[User]: {content}")
        else:
            parts.append(f"[Assistant]: {content}")
    return "\n\n".join(parts)


async def ollama_chat(
    messages: List[Dict[str, str]],
    model: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
) -> str:
    """Non-streaming chat via Ollama using /api/generate."""
    client = get_client()
    model = await _get_ollama_model(model)
    prompt = _messages_to_prompt(messages)
    body = {"model": model, "prompt": prompt, "stream": False}
    options: Dict[str, Any] = {}
    if temperature is not None:
        options["temperature"] = temperature
    if top_p is not None:
        options["top_p"] = top_p
    if options:
        body["options"] = options
    resp = await client.post(f"{config.OLLAMA_URL}/api/generate", json=body, timeout=60.0)
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", "")


async def lmstudio_chat(
    messages: List[Dict[str, str]],
    model: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
) -> str:
    """Non-streaming chat via LM Studio."""
    client = get_client()
    body = {"model": model or "local-model", "messages": messages, "stream": False}
    if temperature is not None:
        body["temperature"] = temperature
    if top_p is not None:
        body["top_p"] = top_p
    resp = await client.post(f"{config.LMSTUDIO_URL}/v1/chat/completions", json=body, timeout=60.0)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


async def ollama_chat_stream(
    messages: List[Dict[str, str]],
    model: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
) -> AsyncGenerator[str, None]:
    """Streaming chat via Ollama /api/generate — yields text chunks."""
    client = get_client()
    model = await _get_ollama_model(model)
    prompt = _messages_to_prompt(messages)
    body = {"model": model, "prompt": prompt, "stream": True}
    options: Dict[str, Any] = {}
    if temperature is not None:
        options["temperature"] = temperature
    if top_p is not None:
        options["top_p"] = top_p
    if options:
        body["options"] = options
    async with client.stream("POST", f"{config.OLLAMA_URL}/api/generate", json=body, timeout=60.0) as resp:
        async for chunk in resp.aiter_text():
            for line in chunk.split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    text = data.get("response", "")
                    if text:
                        yield text
                except json.JSONDecodeError:
                    pass


async def lmstudio_chat_stream(
    messages: List[Dict[str, str]],
    model: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
) -> AsyncGenerator[str, None]:
    """Streaming chat via LM Studio — yields text chunks."""
    client = get_client()
    body = {"model": model or "local-model", "messages": messages, "stream": True}
    if temperature is not None:
        body["temperature"] = temperature
    if top_p is not None:
        body["top_p"] = top_p
    async with client.stream("POST", f"{config.LMSTUDIO_URL}/v1/chat/completions", json=body, timeout=60.0) as resp:
        async for chunk in resp.aiter_text():
            for line in chunk.split("\n"):
                line = line.strip()
                if line.startswith("data: "):
                    payload = line[6:]
                    if payload == "[DONE]":
                        continue
                    try:
                        data = json.loads(payload)
                        text = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if text:
                            yield text
                    except json.JSONDecodeError:
                        pass
