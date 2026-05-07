"""OpenAI-compatible integration — supports OpenAI, Kimi, Groq, and any other compatible provider."""
import json
import logging
from typing import Any, AsyncGenerator, Dict, List

import httpx

from core import config

logger = logging.getLogger(__name__)


DEFAULT_BASE_URL = "https://api.openai.com/v1"


def _get_base_url() -> str:
    return config.OPENAI_BASE_URL or DEFAULT_BASE_URL


def _get_api_key() -> str:
    return config.OPENAI_API_KEY or config.KIMI_API_KEY or ""


def is_configured() -> bool:
    return bool(_get_api_key())


def _get_headers() -> dict:
    return {
        "authorization": f"Bearer {_get_api_key()}",
        "content-type": "application/json",
    }


async def openai_chat(
    messages: List[Dict[str, str]],
    model: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
) -> str:
    """Non-streaming chat via OpenAI-compatible API."""
    if not is_configured():
        raise RuntimeError("OpenAI-compatible API key not configured")

    body: Dict[str, Any] = {
        "model": model or "gpt-4o-mini",
        "messages": messages,
    }
    if temperature is not None:
        body["temperature"] = temperature
    if top_p is not None:
        body["top_p"] = top_p

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        resp = await client.post(f"{_get_base_url()}/chat/completions", headers=_get_headers(), json=body)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def openai_chat_stream(
    messages: List[Dict[str, str]],
    model: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
) -> AsyncGenerator[str, None]:
    """Streaming chat via OpenAI-compatible API."""
    if not is_configured():
        raise RuntimeError("OpenAI-compatible API key not configured")

    body: Dict[str, Any] = {
        "model": model or "gpt-4o-mini",
        "messages": messages,
        "stream": True,
    }
    if temperature is not None:
        body["temperature"] = temperature
    if top_p is not None:
        body["top_p"] = top_p

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        async with client.stream("POST", f"{_get_base_url()}/chat/completions", headers=_get_headers(), json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        continue
                    try:
                        event = json.loads(payload)
                        delta = event.get("choices", [{}])[0].get("delta", {})
                        text = delta.get("content", "")
                        if text:
                            yield text
                    except json.JSONDecodeError:
                        pass


async def detect_openai_models() -> List[Dict[str, Any]]:
    """Discover available models from the OpenAI-compatible API."""
    if not is_configured():
        return []
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
            resp = await client.get(f"{_get_base_url()}/models", headers=_get_headers())
            if resp.status_code == 200:
                data = resp.json()
                models = []
                for m in data.get("data", []):
                    name = m.get("id", "unknown")
                    models.append({"name": name, "provider": "openai_compatible", "id": name})
                return models
    except Exception as e:
        logger.debug(f"OpenAI-compatible API not reachable: {e}")
    return []
