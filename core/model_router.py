"""
Model Router — routes requests to local or cloud LLMs based on API mode lockout.
Respects explicit model selection when provided.
Supports orchestrator model selection and subagent mode routing.
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
from integrations.claude import claude_chat, claude_chat_stream, is_configured as claude_configured
from integrations.openai_compatible import (
    openai_chat,
    openai_chat_stream,
    is_configured as openai_configured,
    detect_openai_models,
)

logger = logging.getLogger(__name__)


def _is_cloud_model(model: str | None) -> bool:
    """Heuristic: does this model name/id refer to a cloud provider?"""
    if not model:
        return False
    m = model.lower()
    return any(p in m for p in ("gemini", "gpt-", "claude", "openai", "google", "azure", "anthropic", "kimi"))


def _is_local_model(model: str | None) -> bool:
    """Heuristic: does this model name/id refer to a local provider?"""
    if not model:
        return False
    m = model.lower()
    return any(p in m for p in ("ollama", "lmstudio", "local", ":"))


def _model_to_provider(model: str | None) -> str:
    """Determine provider from model name."""
    if not model:
        return "auto"
    m = model.lower()
    if "claude" in m:
        return "claude"
    if "gemini" in m or "google" in m:
        return "gemini"
    if "gpt-" in m or "openai" in m or "kimi" in m:
        return "openai"
    if ":" in m or "ollama" in m:
        return "ollama"
    if "lmstudio" in m:
        return "lmstudio"
    return "auto"


class ModelRouter:
    def __init__(self):
        self.mode = config.API_MODE

    async def chat(
        self,
        messages: list,
        model: str | None = None,
        mode: str = "ask",
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> str:
        """Non-streaming chat. Returns full response text."""
        if model:
            return await self._explicit_model_chat(messages, model, temperature=temperature, top_p=top_p)
        if self.mode == "local_only":
            return await self._local_chat(messages, temperature=temperature, top_p=top_p)
        elif self.mode == "cloud_only":
            return await self._cloud_chat(messages, temperature=temperature, top_p=top_p)
        else:
            return await self._hybrid_chat(messages, mode, temperature=temperature, top_p=top_p)

    async def chat_stream(
        self,
        messages: list,
        model: str | None = None,
        mode: str = "ask",
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming chat. Yields text chunks."""
        if model:
            async for chunk in self._explicit_model_chat_stream(messages, model, temperature=temperature, top_p=top_p):
                yield chunk
            return
        if self.mode == "local_only":
            async for chunk in self._local_chat_stream(messages, temperature=temperature, top_p=top_p):
                yield chunk
        elif self.mode == "cloud_only":
            async for chunk in self._cloud_chat_stream(messages, temperature=temperature, top_p=top_p):
                yield chunk
        else:
            if mode in ("swarm", "plan"):
                try:
                    async for chunk in self._cloud_chat_stream(messages, temperature=temperature, top_p=top_p):
                        yield chunk
                except Exception:
                    async for chunk in self._local_chat_stream(messages, temperature=temperature, top_p=top_p):
                        yield chunk
            else:
                try:
                    async for chunk in self._local_chat_stream(messages, temperature=temperature, top_p=top_p):
                        yield chunk
                except Exception:
                    async for chunk in self._cloud_chat_stream(messages, temperature=temperature, top_p=top_p):
                        yield chunk

    async def _explicit_model_chat(
        self,
        messages: list,
        model: str,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> str:
        """Route to the correct provider based on explicit model selection."""
        provider = _model_to_provider(model)
        errors = []

        if provider == "claude" and claude_configured():
            try:
                return await claude_chat(messages, model=model, temperature=temperature, top_p=top_p)
            except Exception as e:
                errors.append(f"Claude: {e}")
        elif provider == "openai" and openai_configured():
            try:
                return await openai_chat(messages, model=model, temperature=temperature, top_p=top_p)
            except Exception as e:
                errors.append(f"OpenAI: {e}")
        elif provider == "gemini" and gemini_configured():
            try:
                return await gemini_chat(messages, temperature=temperature, top_p=top_p)
            except Exception as e:
                errors.append(f"Gemini: {e}")

        if _is_cloud_model(model):
            # Fallback: try all cloud providers
            if claude_configured():
                try:
                    return await claude_chat(messages, model=model, temperature=temperature, top_p=top_p)
                except Exception as e:
                    errors.append(f"Claude: {e}")
            if openai_configured():
                try:
                    return await openai_chat(messages, model=model, temperature=temperature, top_p=top_p)
                except Exception as e:
                    errors.append(f"OpenAI: {e}")
            if gemini_configured():
                try:
                    return await gemini_chat(messages, temperature=temperature, top_p=top_p)
                except Exception as e:
                    errors.append(f"Gemini: {e}")
            return f"[Cloud API Error] {' | '.join(errors)} — check API keys."
        else:
            # Try Ollama first, then LM Studio
            try:
                return await ollama_chat(messages, model=model, temperature=temperature, top_p=top_p)
            except Exception as e:
                errors.append(f"Ollama: {e}")
            try:
                return await lmstudio_chat(messages, model=model, temperature=temperature, top_p=top_p)
            except Exception as e:
                errors.append(f"LM Studio: {e}")
            return f"[Local LLM Error] {' | '.join(errors)}"

    async def _explicit_model_chat_stream(
        self,
        messages: list,
        model: str,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream from the correct provider based on explicit model selection."""
        provider = _model_to_provider(model)

        if provider == "claude" and claude_configured():
            try:
                async for chunk in claude_chat_stream(messages, model=model, temperature=temperature, top_p=top_p):
                    yield chunk
                return
            except Exception as e:
                yield f"[Cloud API Error] Claude: {e}"
                return
        elif provider == "openai" and openai_configured():
            try:
                async for chunk in openai_chat_stream(messages, model=model, temperature=temperature, top_p=top_p):
                    yield chunk
                return
            except Exception as e:
                yield f"[Cloud API Error] OpenAI: {e}"
                return
        elif provider == "gemini" and gemini_configured():
            try:
                result = await gemini_chat(messages, temperature=temperature, top_p=top_p)
                for word in result.split(" "):
                    yield word + " "
                return
            except Exception as e:
                yield f"[Cloud API Error] Gemini: {e}"
                return

        if _is_cloud_model(model):
            if claude_configured():
                try:
                    async for chunk in claude_chat_stream(messages, model=model, temperature=temperature, top_p=top_p):
                        yield chunk
                    return
                except Exception as e:
                    yield f"[Cloud API Error] Claude: {e}"
                    return
            if openai_configured():
                try:
                    async for chunk in openai_chat_stream(messages, model=model, temperature=temperature, top_p=top_p):
                        yield chunk
                    return
                except Exception as e:
                    yield f"[Cloud API Error] OpenAI: {e}"
                    return
            if gemini_configured():
                try:
                    result = await gemini_chat(messages, temperature=temperature, top_p=top_p)
                    for word in result.split(" "):
                        yield word + " "
                    return
                except Exception as e:
                    yield f"[Cloud API Error] Gemini: {e}"
                    return
            yield "[Cloud API Error] No cloud API configured."
            return
        else:
            try:
                async for chunk in ollama_chat_stream(messages, model=model, temperature=temperature, top_p=top_p):
                    yield chunk
                return
            except Exception as e_ollama:
                try:
                    async for chunk in lmstudio_chat_stream(messages, model=model, temperature=temperature, top_p=top_p):
                        yield chunk
                    return
                except Exception as e_lm:
                    yield f"[Local LLM Error] Ollama: {e_ollama} | LM Studio: {e_lm}"

    async def _local_chat(
        self,
        messages: list,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> str:
        errors = []
        try:
            return await ollama_chat(messages, temperature=temperature, top_p=top_p)
        except Exception as e:
            errors.append(f"Ollama: {e}")
        try:
            return await lmstudio_chat(messages, temperature=temperature, top_p=top_p)
        except Exception as e:
            errors.append(f"LM Studio: {e}")
        return f"[Local LLM Error] {' | '.join(errors)}"

    async def _cloud_chat(
        self,
        messages: list,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> str:
        errors = []
        if claude_configured():
            try:
                return await claude_chat(messages, temperature=temperature, top_p=top_p)
            except Exception as e:
                errors.append(f"Claude: {e}")
        if openai_configured():
            try:
                return await openai_chat(messages, temperature=temperature, top_p=top_p)
            except Exception as e:
                errors.append(f"OpenAI: {e}")
        if gemini_configured():
            try:
                return await gemini_chat(messages, temperature=temperature, top_p=top_p)
            except Exception as e:
                errors.append(f"Gemini: {e}")
        return f"[Cloud API Error] {' | '.join(errors)} — check API keys."

    async def _hybrid_chat(
        self,
        messages: list,
        mode: str,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> str:
        if mode in ("swarm", "plan"):
            try:
                return await self._cloud_chat(messages, temperature=temperature, top_p=top_p)
            except Exception:
                pass
            return await self._local_chat(messages, temperature=temperature, top_p=top_p)
        else:
            try:
                return await ollama_chat(messages, temperature=temperature, top_p=top_p)
            except Exception:
                try:
                    return await self._cloud_chat(messages, temperature=temperature, top_p=top_p)
                except Exception:
                    pass
                return await self._local_chat(messages, temperature=temperature, top_p=top_p)

    async def _local_chat_stream(
        self,
        messages: list,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> AsyncGenerator[str, None]:
        try:
            async for chunk in ollama_chat_stream(messages, temperature=temperature, top_p=top_p):
                yield chunk
        except Exception as e_ollama:
            try:
                async for chunk in lmstudio_chat_stream(messages, temperature=temperature, top_p=top_p):
                    yield chunk
            except Exception as e_lm:
                yield f"[Local LLM Error] Ollama: {e_ollama} | LM Studio: {e_lm}"

    async def _cloud_chat_stream(
        self,
        messages: list,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> AsyncGenerator[str, None]:
        if claude_configured():
            try:
                async for chunk in claude_chat_stream(messages, temperature=temperature, top_p=top_p):
                    yield chunk
                return
            except Exception:
                pass
        if openai_configured():
            try:
                async for chunk in openai_chat_stream(messages, temperature=temperature, top_p=top_p):
                    yield chunk
                return
            except Exception:
                pass
        if gemini_configured():
            try:
                result = await gemini_chat(messages, temperature=temperature, top_p=top_p)
                for word in result.split(" "):
                    yield word + " "
                return
            except Exception as e:
                yield f"[Cloud API Error] Gemini: {e}"
                return
        yield "[Cloud API Error] No cloud API configured."


router = ModelRouter()


# Functions expected by modes/*.py

async def discover_local_models() -> list:
    ollama = await detect_ollama_models()
    lmstudio = await detect_lmstudio_models()
    return ollama + lmstudio


async def discover_cloud_models() -> list:
    models = []
    if claude_configured():
        models.append({
            "id": "claude-3-5-sonnet-20241022",
            "provider": "anthropic",
            "name": "Claude 3.5 Sonnet",
        })
        models.append({
            "id": "claude-3-opus-20240229",
            "provider": "anthropic",
            "name": "Claude 3 Opus",
        })
    if openai_configured():
        openai_models = await detect_openai_models()
        models.extend(openai_models)
        # Add known defaults if detection failed
        if not openai_models:
            models.append({
                "id": "gpt-4o",
                "provider": "openai_compatible",
                "name": "GPT-4o",
            })
            models.append({
                "id": "gpt-4o-mini",
                "provider": "openai_compatible",
                "name": "GPT-4o Mini",
            })
    if gemini_configured():
        models.append({
            "id": config.CLOUD_MODEL,
            "provider": "google",
            "name": config.CLOUD_MODEL,
        })
    return models


async def select_model(prefer_local: bool = True, subagent_mode: str | None = None) -> str:
    mode = subagent_mode or config.SUBAGENT_MODE
    if config.API_MODE == "local_only":
        return config.LOCAL_MODEL
    elif config.API_MODE == "cloud_only":
        return config.CLOUD_MODEL
    else:
        if mode == "local":
            return config.LOCAL_MODEL
        elif mode == "cloud":
            return config.ORCHESTRATOR_MODEL or config.CLOUD_MODEL
        else:
            return config.LOCAL_MODEL if prefer_local else (config.ORCHESTRATOR_MODEL or config.CLOUD_MODEL)


async def chat_completion(
    messages: list,
    model: Optional[str] = None,
    stream: bool = False,
    temperature: float | None = None,
    top_p: float | None = None,
) -> AsyncGenerator[str, None]:
    if temperature is None:
        temperature = config.TEMPERATURE
    if stream:
        async for chunk in router.chat_stream(messages, model=model, temperature=temperature, top_p=top_p):
            yield chunk
    else:
        full = await router.chat(messages, model=model, temperature=temperature, top_p=top_p)
        yield full
