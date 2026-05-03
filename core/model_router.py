"""
Model Router — routes requests to local or cloud LLMs based on API mode lockout.
"""
import logging
from typing import Optional, AsyncGenerator

from . import config
from integrations.llm import (
    detect_ollama_models,
    detect_lmstudio_models,
    ollama_chat,
    lmstudio_chat,
    ollama_chat_stream,
    lmstudio_chat_stream,
)
from integrations.gemini import gemini_chat, is_configured as gemini_configured

logger = logging.getLogger(__name__)


class ModelRouter:
    def __init__(self):
        self.mode = config.API_MODE

    async def chat(self, messages: list, mode: str = "ask") -> str:
        """Non-streaming chat. Returns full response text."""
        if self.mode == "local-only":
            return await self._local_chat(messages)
        elif self.mode == "cloud-only":
            return await self._cloud_chat(messages)
        else:
            return await self._hybrid_chat(messages, mode)

    async def chat_stream(self, messages: list, mode: str = "ask") -> AsyncGenerator[str, None]:
        """Streaming chat. Yields text chunks."""
        if self.mode == "local-only":
            async for chunk in self._local_chat_stream(messages):
                yield chunk
        elif self.mode == "cloud-only":
            async for chunk in self._cloud_chat_stream(messages):
                yield chunk
        else:
            if mode in ("swarm", "plan"):
                try:
                    async for chunk in self._cloud_chat_stream(messages):
                        yield chunk
                except Exception:
                    async for chunk in self._local_chat_stream(messages):
                        yield chunk
            else:
                try:
                    async for chunk in self._local_chat_stream(messages):
                        yield chunk
                except Exception:
                    async for chunk in self._cloud_chat_stream(messages):
                        yield chunk

    async def _local_chat(self, messages: list) -> str:
        errors = []
        try:
            return await ollama_chat(messages)
        except Exception as e:
            errors.append(f"Ollama: {e}")
        try:
            return await lmstudio_chat(messages)
        except Exception as e:
            errors.append(f"LM Studio: {e}")
        return f"[Local LLM Error] {' | '.join(errors)}"

    async def _cloud_chat(self, messages: list) -> str:
        errors = []
        if gemini_configured():
            try:
                return await gemini_chat(messages)
            except Exception as e:
                errors.append(f"Gemini: {e}")
        return f"[Cloud API Error] {' | '.join(errors)} — check API keys."

    async def _hybrid_chat(self, messages: list, mode: str) -> str:
        if mode in ("swarm", "plan"):
            try:
                if gemini_configured():
                    return await gemini_chat(messages)
            except Exception:
                pass
            return await self._local_chat(messages)
        else:
            try:
                return await ollama_chat(messages)
            except Exception:
                try:
                    if gemini_configured():
                        return await gemini_chat(messages)
                except Exception:
                    pass
                return await self._local_chat(messages)

    async def _local_chat_stream(self, messages: list) -> AsyncGenerator[str, None]:
        try:
            async for chunk in ollama_chat_stream(messages):
                yield chunk
        except Exception as e_ollama:
            try:
                async for chunk in lmstudio_chat_stream(messages):
                    yield chunk
            except Exception as e_lm:
                yield f"[Local LLM Error] Ollama: {e_ollama} | LM Studio: {e_lm}"

    async def _cloud_chat_stream(self, messages: list) -> AsyncGenerator[str, None]:
        if gemini_configured():
            try:
                result = await gemini_chat(messages)
                # Simulate streaming by yielding word-by-word
                for word in result.split(" "):
                    yield word + " "
            except Exception as e:
                yield f"[Cloud API Error] Gemini: {e}"
        else:
            yield "[Cloud API Error] No cloud API configured."


router = ModelRouter()


# Functions expected by modes/*.py

async def discover_local_models() -> list:
    ollama = await detect_ollama_models()
    lmstudio = await detect_lmstudio_models()
    return ollama + lmstudio


async def discover_cloud_models() -> list:
    models = []
    if gemini_configured():
        models.append({
            "id": config.CLOUD_MODEL,
            "provider": "google",
            "name": config.CLOUD_MODEL,
        })
    return models


async def select_model(prefer_local: bool = True) -> str:
    if config.API_MODE == "local-only":
        return config.LOCAL_MODEL
    elif config.API_MODE == "cloud-only":
        return config.CLOUD_MODEL
    else:
        return config.LOCAL_MODEL if prefer_local else config.CLOUD_MODEL


async def chat_completion(
    messages: list,
    model: Optional[str] = None,
    stream: bool = False,
) -> AsyncGenerator[str, None]:
    if stream:
        async for chunk in router.chat_stream(messages):
            yield chunk
    else:
        full = await router.chat(messages)
        yield full
