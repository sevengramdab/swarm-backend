"""Anthropic Claude integration — Cloud LLM provider for the swarm."""
import json
import logging
from typing import Any, AsyncGenerator, Dict, List

import httpx

from core import config

logger = logging.getLogger(__name__)


CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"


def is_configured() -> bool:
    return bool(config.CLAUDE_API_KEY)


def _get_headers() -> dict:
    return {
        "x-api-key": config.CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }


def _convert_messages(messages: List[Dict[str, str]]) -> tuple:
    """Convert generic messages to Anthropic format. Extract system prompt separately."""
    system_text = ""
    claude_messages = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            system_text += content + "\n"
        elif role == "user":
            claude_messages.append({"role": "user", "content": content})
        else:
            claude_messages.append({"role": "assistant", "content": content})
    # Ensure alternating user/assistant
    cleaned = []
    last_role = None
    for m in claude_messages:
        if m["role"] == last_role:
            cleaned[-1]["content"] += "\n" + m["content"]
        else:
            cleaned.append(m)
            last_role = m["role"]
    return system_text.strip(), cleaned


async def claude_chat(
    messages: List[Dict[str, str]],
    model: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
) -> str:
    """Non-streaming chat via Anthropic Claude."""
    if not config.CLAUDE_API_KEY:
        raise RuntimeError("Claude API key not configured")

    system_text, claude_messages = _convert_messages(messages)
    body: Dict[str, Any] = {
        "model": model or "claude-3-5-sonnet-20241022",
        "max_tokens": 4096,
        "messages": claude_messages,
    }
    if system_text:
        body["system"] = system_text
    if temperature is not None:
        body["temperature"] = temperature
    if top_p is not None:
        body["top_p"] = top_p

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        resp = await client.post(CLAUDE_API_URL, headers=_get_headers(), json=body)
        resp.raise_for_status()
        data = resp.json()
        content_blocks = data.get("content", [])
        text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
        return text


async def claude_chat_stream(
    messages: List[Dict[str, str]],
    model: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
) -> AsyncGenerator[str, None]:
    """Streaming chat via Anthropic Claude."""
    if not config.CLAUDE_API_KEY:
        raise RuntimeError("Claude API key not configured")

    system_text, claude_messages = _convert_messages(messages)
    body: Dict[str, Any] = {
        "model": model or "claude-3-5-sonnet-20241022",
        "max_tokens": 4096,
        "messages": claude_messages,
        "stream": True,
    }
    if system_text:
        body["system"] = system_text
    if temperature is not None:
        body["temperature"] = temperature
    if top_p is not None:
        body["top_p"] = top_p

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        async with client.stream("POST", CLAUDE_API_URL, headers=_get_headers(), json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        continue
                    try:
                        event = json.loads(payload)
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                text = delta.get("text", "")
                                if text:
                                    yield text
                    except json.JSONDecodeError:
                        pass
