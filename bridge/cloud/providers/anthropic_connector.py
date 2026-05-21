"""
Anthropic Connector - The dimmer switch that chats with Claude's brain.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from pydantic import Field

from providers.base import (
    BaseProvider,
    InferenceRequest,
    InferenceResponse,
    ProviderConfig,
    ProviderError,
    RateLimitError,
    AuthenticationError,
)


class AnthropicConfig(ProviderConfig):
    """
    The special remote-control codes for Claude's house.
    """
    api_version: str = Field(default="2023-06-01", description="Which year's wiring diagram to use.")
    max_tokens: int = Field(default=1024, description="How bright the bulb is allowed to get.")


class AnthropicConnector(BaseProvider):
    """
    A garage-door opener that only works on Claude's mansion.
    """

    def __init__(self, config: AnthropicConfig, http_client: Optional[httpx.AsyncClient] = None) -> None:
        """
        Program the garage-door opener with Claude's secret frequency.

        Args:
            config: The instruction manual for Claude's house.
            http_client: A pre-stretched extension cord, or None to buy a new one.
        """
        super().__init__(config, http_client)
        self.config: AnthropicConfig = config
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "x-api-key": config.api_key,
                    "anthropic-version": config.api_version,
                    "Content-Type": "application/json",
                },
                timeout=config.timeout,
                base_url=config.base_url or "https://api.anthropic.com/v1",
            )

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        """
        Ring Claude's doorbell and ask a question through the intercom.

        Args:
            request: The note we slide through the mail slot.

        Returns:
            The polite note Claude slides back.
        """
        payload = self._build_payload(request)
        response = await self._client.post("messages", json=payload)
        await self._raise_for_status(response)
        data = response.json()
        return self._parse_response(data)

    async def stream_generate(self, request: InferenceRequest) -> AsyncIterator[str]:
        """
        Turn on the garden sprinkler so each word sprays out one at a time.

        Args:
            request: The note we slide through the mail slot.

        Yields:
            Each droplet of text as it hits the lawn.
        """
        payload = self._build_payload(request, stream=True)
        async with self._client.stream("POST", "messages", json=payload) as response:
            await self._raise_for_status(response)
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line.removeprefix("data: ")
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("delta", {})
                        text = delta.get("text", "")
                        if text:
                            yield text
                    except json.JSONDecodeError:
                        continue

    async def health_check(self) -> bool:
        """
        Knock on Claude's door to see if anyone is home.

        Returns:
            True if the porch light is on, False if the house is dark.
        """
        try:
            response = await self._client.get("models")
            return response.status_code == 200
        except Exception:
            return False

    def _build_payload(self, request: InferenceRequest, stream: bool = False) -> Dict[str, Any]:
        """
        Fold the letter into the exact envelope size Claude likes.

        Args:
            request: The raw scribbles we want to send.
            stream: Whether we want a slow drip or a full bucket.

        Returns:
            A perfectly folded paper airplane ready to throw.
        """
        content: List[Dict[str, Any]] = [{"type": "text", "text": request.prompt}]
        if request.images:
            for img in request.images:
                content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img}})

        payload: Dict[str, Any] = {
            "model": request.model or self.config.default_model,
            "max_tokens": request.max_tokens or self.config.max_tokens,
            "messages": [{"role": "user", "content": content}],
            "temperature": request.temperature,
            "stream": stream,
        }
        if request.tools:
            payload["tools"] = request.tools
        if request.extra_params:
            payload.update(request.extra_params)
        return payload

    async def _raise_for_status(self, response: httpx.Response) -> None:
        """
        Read the face of the mail carrier; if they look mad, find out why.

        Args:
            response: The expression on the carrier's face.

        Raises:
            RateLimitError: If Claude's mailbox is stuffed full.
            AuthenticationError: If Claude changed the locks.
            ProviderError: If a tree fell on the power line.
        """
        if response.status_code == 200:
            return
        if response.status_code == 429:
            raise RateLimitError("Claude's fuse blew: rate limit hit.")
        if response.status_code in (401, 403):
            raise AuthenticationError("Claude's gate is locked: bad key.")
        try:
            body = response.json()
            message = body.get("error", {}).get("message", "Unknown Claude error")
        except Exception:
            message = response.text or "Unknown Claude error"
        raise ProviderError(f"Claude's wiring sparked ({response.status_code}): {message}")

    def _parse_response(self, data: Dict[str, Any]) -> InferenceResponse:
        """
        Unwrap the present Claude left on the porch.

        Args:
            data: The gift-wrapped box.

        Returns:
            The toy inside, catalogued and labeled.
        """
        content_blocks = data.get("content", [])
        text_parts: List[str] = []
        tool_calls: Optional[List[Dict[str, Any]]] = None
        for block in content_blocks:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                if tool_calls is None:
                    tool_calls = []
                tool_calls.append({
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "input": block.get("input"),
                })
        usage = data.get("usage", {})
        return InferenceResponse(
            text="\n".join(text_parts),
            model=data.get("model", self.config.default_model),
            provider="anthropic",
            usage={
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            },
            finish_reason=data.get("stop_reason"),
            tool_calls=tool_calls,
        )
