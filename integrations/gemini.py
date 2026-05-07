"""Gemini integration — Cloud offload for the Hybrid Swarm."""
import logging
from typing import Any, Dict, List

from core import config

logger = logging.getLogger(__name__)

_genai: Any = None
_model: Any = None


def _get_model() -> Any:
    global _genai, _model
    if _model is not None:
        return _model
    if not config.GEMINI_API_KEY:
        raise RuntimeError("Gemini API key not configured")
    try:
        import google.generativeai as genai
        _genai = genai
        genai.configure(api_key=config.GEMINI_API_KEY)
        _model = genai.GenerativeModel(config.CLOUD_MODEL)
        logger.info("[GEMINI] Cloud model initialized")
        return _model
    except ImportError:
        raise RuntimeError("google-generativeai not installed")
    except Exception as e:
        logger.error(f"[GEMINI] Failed to initialize: {e}")
        raise


def is_configured() -> bool:
    return bool(config.GEMINI_API_KEY)


async def gemini_chat(
    messages: List[Dict[str, str]],
    temperature: float | None = None,
    top_p: float | None = None,
) -> str:
    """Non-streaming chat via Gemini."""
    model = _get_model()
    history = []
    for msg in messages[:-1]:
        role = "user" if msg.get("role") == "user" else "model"
        history.append({"role": role, "parts": [msg.get("content", "")]})
    chat = model.start_chat(history=history)
    last_msg = messages[-1].get("content", "") if messages else ""
    gen_config_kwargs: Dict[str, Any] = {}
    if temperature is not None:
        gen_config_kwargs["temperature"] = temperature
    if top_p is not None:
        gen_config_kwargs["top_p"] = top_p
    kwargs: Dict[str, Any] = {}
    if gen_config_kwargs:
        kwargs["generation_config"] = _genai.types.GenerationConfig(**gen_config_kwargs)
    response = await chat.send_message_async(last_msg, **kwargs)
    return response.text if hasattr(response, "text") else str(response)


async def gemini_generate(
    prompt: str,
    system_prompt: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
) -> str:
    """Simple non-streaming generate via Gemini."""
    model = _get_model()
    full = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    gen_config_kwargs: Dict[str, Any] = {}
    if temperature is not None:
        gen_config_kwargs["temperature"] = temperature
    if top_p is not None:
        gen_config_kwargs["top_p"] = top_p
    kwargs: Dict[str, Any] = {}
    if gen_config_kwargs:
        kwargs["generation_config"] = _genai.types.GenerationConfig(**gen_config_kwargs)
    response = await model.generate_content_async(full, **kwargs)
    return response.text if hasattr(response, "text") else str(response)
