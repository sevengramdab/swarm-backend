"""
Model Router — routes requests to local or cloud LLMs based on API mode lockout.
"""
import os
from typing import Optional, AsyncGenerator

from . import config

class ModelRouter:
    def __init__(self):
        self.mode = config.API_MODE  # local-only | cloud-only | hybrid

    async def chat(self, messages: list, mode: str = "ask") -> str:
        if self.mode == "local-only":
            return await self._local_chat(messages)
        elif self.mode == "cloud-only":
            return await self._cloud_chat(messages)
        else:  # hybrid
            return await self._hybrid_chat(messages, mode)

    async def _local_chat(self, messages: list) -> str:
        try:
            return await self._ollama_chat(messages)
        except Exception:
            try:
                return await self._lmstudio_chat(messages)
            except Exception as e:
                return f"[Local LLM Error] {str(e)} — check Ollama or LM Studio."

    async def _cloud_chat(self, messages: list) -> str:
        try:
            return await self._gemini_chat(messages)
        except Exception:
            try:
                return await self._copilot_chat(messages)
            except Exception as e:
                return f"[Cloud API Error] {str(e)} — check API keys."

    async def _hybrid_chat(self, messages: list, mode: str) -> str:
        if mode in ("swarm", "plan"):
            try:
                return await self._gemini_chat(messages)
            except Exception:
                return await self._local_chat(messages)
        else:
            try:
                return await self._ollama_chat(messages)
            except Exception:
                return await self._cloud_chat(messages)

    async def _ollama_chat(self, messages: list) -> str:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{config.OLLAMA_URL}/api/chat",
                json={"model": config.LOCAL_MODEL, "messages": messages, "stream": False}
            ) as resp:
                data = await resp.json()
                return data.get("message", {}).get("content", "")

    async def _lmstudio_chat(self, messages: list) -> str:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{config.LMSTUDIO_URL}/v1/chat/completions",
                json={"model": "local-model", "messages": messages, "stream": False}
            ) as resp:
                data = await resp.json()
                return data["choices"][0]["message"]["content"]

    async def _gemini_chat(self, messages: list) -> str:
        import aiohttp
        key = config.GEMINI_API_KEY
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set")
        contents = []
        for m in messages:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{config.CLOUD_MODEL}:generateContent?key={key}",
                json={"contents": contents}
            ) as resp:
                data = await resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]

    async def _copilot_chat(self, messages: list) -> str:
        raise RuntimeError("Copilot chat not yet implemented — use Gemini or local LLMs")


# Global router instance
router = ModelRouter()


# Functions expected by modes/*.py

async def discover_local_models() -> list:
    """Discover available local models."""
    models = []
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{config.OLLAMA_URL}/api/tags") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for m in data.get("models", []):
                        models.append({
                            "id": m.get("name", "unknown"),
                            "provider": "ollama",
                            "name": m.get("name", "unknown"),
                        })
    except Exception:
        pass
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{config.LMSTUDIO_URL}/v1/models") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for m in data.get("data", []):
                        models.append({
                            "id": m.get("id", "unknown"),
                            "provider": "lmstudio",
                            "name": m.get("id", "unknown"),
                        })
    except Exception:
        pass
    return models


async def discover_cloud_models() -> list:
    """Discover available cloud models."""
    models = []
    if config.GEMINI_API_KEY:
        models.append({
            "id": config.CLOUD_MODEL,
            "provider": "google",
            "name": config.CLOUD_MODEL,
        })
    return models


async def select_model(prefer_local: bool = True) -> str:
    """Select the best available model based on API mode."""
    if config.API_MODE == "local-only":
        return config.LOCAL_MODEL
    elif config.API_MODE == "cloud-only":
        return config.CLOUD_MODEL
    else:
        if prefer_local:
            return config.LOCAL_MODEL
        return config.CLOUD_MODEL


async def chat_completion(
    messages: list,
    model: Optional[str] = None,
    stream: bool = False,
) -> AsyncGenerator[str, None]:
    """Generate chat completion. Yields chunks if stream=True, else full response."""
    if not stream:
        full = await router.chat(messages)
        yield full
        return

    # Simulate streaming by yielding word-by-word
    full = await router.chat(messages)
    words = full.split(" ")
    for word in words:
        yield word + " "
