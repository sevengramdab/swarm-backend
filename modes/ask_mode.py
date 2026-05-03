"""Ask Mode — Direct Q&A with the LLM. Simple, single-turn or multi-turn chat."""

import json
from typing import List, Dict, Any, AsyncGenerator
from core.model_router import chat_completion, select_model


SYSTEM_PROMPT = """You are OrbitScribe's Ask Mode assistant. You answer questions directly and concisely.
You have access to the user's VS Code workspace context when provided.
Be helpful, accurate, and to the point."""


async def ask(
    question: str,
    history: List[Dict[str, str]] = None,
    workspace_context: str = "",
    stream: bool = True,
) -> AsyncGenerator[str, None]:
    """Answer a direct question."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    if workspace_context:
        messages.append({
            "role": "system",
            "content": f"Current workspace context:\n{workspace_context}",
        })
    
    if history:
        messages.extend(history)
    
    messages.append({"role": "user", "content": question})
    
    model = await select_model(prefer_local=True)
    async for chunk in chat_completion(messages, model=model, stream=stream):
        yield chunk
