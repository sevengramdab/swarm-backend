"""
Model Router — routes requests to local or cloud LLMs based on API mode lockout.
"""
import os
from typing import Optional

API_MODE = os.environ.get("SWARM_API_MODE", "hybrid").lower()

class ModelRouter:
    def __init__(self):
        self.mode = API_MODE  # local-only | cloud-only | hybrid

    async def chat(self, messages: list, mode: str = "ask") -> str:
        if self.mode == "local-only":
            return await self._local_chat(messages)
        elif self.mode == "cloud-only":
            return await self._cloud_chat(messages)
        else:  # hybrid
            return await self._hybrid_chat(messages, mode)

    async def _local_chat(self, messages: list) -> str:
        # Try Ollama first, then LM Studio
        try:
            return await self._ollama_chat(messages)
        except Exception:
            try:
                return await self._lmstudio_chat(messages)
            except Exception as e:
                return f"[Local LLM Error] {str(e)} — check Ollama or LM Studio."

    async def _cloud_chat(self, messages: list) -> str:
        # Try Gemini, then Copilot
        try:
            return await self._gemini_chat(messages)
        except Exception:
            try:
                return await self._copilot_chat(messages)
            except Exception as e:
                return f"[Cloud API Error] {str(e)} — check API keys."

    async def _hybrid_chat(self, messages: list, mode: str) -> str:
        # For swarm/plan: prefer cloud for complex tasks
        # For ask/agent: prefer local for speed
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
                "http://127.0.0.1:11434/api/chat",
                json={"model": "qwen2.5-coder", "messages": messages, "stream": False}
            ) as resp:
                data = await resp.json()
                return data.get("message", {}).get("content", "")

    async def _lmstudio_chat(self, messages: list) -> str:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://127.0.0.1:1234/v1/chat/completions",
                json={"model": "local-model", "messages": messages, "stream": False}
            ) as resp:
                data = await resp.json()
                return data["choices"][0]["message"]["content"]

    async def _gemini_chat(self, messages: list) -> str:
        import aiohttp
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set")
        # Convert to Gemini format
        contents = []
        for m in messages:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}",
                json={"contents": contents}
            ) as resp:
                data = await resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]

    async def _copilot_chat(self, messages: list) -> str:
        # GitHub Copilot Pro via VS Code extension API (simplified)
        raise RuntimeError("Copilot chat not yet implemented — use Gemini or local LLMs")

router = ModelRouter()
