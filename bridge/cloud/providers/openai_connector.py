"""
OpenAI/Azure Connector - The smart switch that talks to the OpenAI power plant.
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


class OpenAIConfig(ProviderConfig):
    """
    Special thermostat settings just for the OpenAI furnace.
    """
    organization: Optional[str] = Field(default=None, description="The neighborhood watch ID.")
    api_version: Optional[str] = Field(default=None, description="Which wiring standard to use for Azure.")


class OpenAIConnector(BaseProvider):
    """
    A remote control that beams orders straight to the OpenAI power station.
    """

    def __init__(self, config: OpenAIConfig, http_client: Optional[httpx.AsyncClient] = None) -> None:
        """
        Insert batteries into the OpenAI remote.

        Args:
            config: The thermostat with OpenAI-specific dials.
            http_client: A spare extension cord; we'll buy a new one if missing.
        """
        super().__init__(config, http_client)
        self.config: OpenAIConfig = config
        if self._client is None:
            headers: Dict[str, str] = {
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            }
            if config.organization:
                headers["OpenAI-Organization"] = config.organization
            if config.api_version:
                headers["api-version"] = config.api_version
            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=config.timeout,
                base_url=config.base_url or "https://api.openai.com/v1",
            )

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        """
        Flip the OpenAI wall switch and wait for the bulb to light up.

        Args:
            request: The sticky note with what we want the brain to do.

        Returns:
            The glowing receipt showing what the brain said back.

        Raises:
            RateLimitError: If the power company throttles us.
            AuthenticationError: If our key doesn't fit the lock.
            ProviderError: If the wiring shorts out.
        """
        payload = self._build_payload(request, stream=False)
        response = await self._post("chat/completions", payload)
        return self._parse_response(response)

    async def stream_generate(self, request: InferenceRequest) -> AsyncIterator[str]:
        """
        Open the tap slowly so each word dribbles out like water from a leaky hose.

        Args:
            request: The sticky note with what we want the brain to do.

        Yields:
            Each drop of text as it splashes out.

        Raises:
            RateLimitError: If the power company throttles us.
            AuthenticationError: If our key doesn't fit the lock.
            ProviderError: If the plumbing bursts.
        """
        payload = self._build_payload(request, stream=True)
        async with self._client.stream("POST", "chat/completions", json=payload) as response:
            await self._raise_for_status(response)
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line.removeprefix("data: ")
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    async def health_check(self) -> bool:
        """
        Peek at the OpenAI fuse box to see if any lights are green.

        Returns:
            True if the fuse box hums happily, False if it's silent.
        """
        try:
            response = await self._client.get("models")
            return response.status_code == 200
        except Exception:
            return False

    def _build_payload(self, request: InferenceRequest, stream: bool) -> Dict[str, Any]:
        """
        Stack the Lego blocks into the exact shape OpenAI expects.

        Args:
            request: The sticky note with instructions.
            stream: Whether we want a fire-hose or a garden-hose.

        Returns:
            A neat dictionary of Lego bricks ready to ship.
        """
        messages: List[Dict[str, Any]] = [{"role": "user", "content": request.prompt}]
        payload: Dict[str, Any] = {
            "model": request.model or self.config.default_model,
            "messages": messages,
            "temperature": request.temperature,
            "stream": stream,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.tools:
            payload["tools"] = request.tools
        if request.extra_params:
            payload.update(request.extra_params)
        return payload

    async def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Slide the envelope under the OpenAI door and wait for a reply.

        Args:
            endpoint: Which mail slot to use.
            payload: The letter inside the envelope.

        Returns:
            The return letter as a dictionary.
        """
        response = await self._client.post(endpoint, json=payload)
        await self._raise_for_status(response)
        return response.json()

    async def _raise_for_status(self, response: httpx.Response) -> None:
        """
        Check the mailbox flag; if it's red, figure out why the mailman was angry.

        Args:
            response: The mailbox contents.

        Raises:
            RateLimitError: If we mailed too many letters today.
            AuthenticationError: If the mailman didn't recognize us.
            ProviderError: For any other postal disaster.
        """
        if response.status_code == 200:
            return
        if response.status_code == 429:
            raise RateLimitError("OpenAI flipped the breaker: too many requests.")
        if response.status_code in (401, 403):
            raise AuthenticationError("OpenAI locked the door: bad key.")
        try:
            body = response.json()
            message = body.get("error", {}).get("message", "Unknown error")
        except Exception:
            message = response.text or "Unknown error"
        raise ProviderError(f"OpenAI shorted out ({response.status_code}): {message}")

    def _parse_response(self, data: Dict[str, Any]) -> InferenceResponse:
        """
        Unfold the origami receipt from OpenAI into a proper Python object.

        Args:
            data: The crumpled paper from the API.

        Returns:
            A shiny InferenceResponse we can stick on the fridge.
        """
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage = data.get("usage", {})
        return InferenceResponse(
            text=message.get("content", ""),
            model=data.get("model", self.config.default_model),
            provider="openai",
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            finish_reason=choice.get("finish_reason"),
            tool_calls=message.get("tool_calls"),
        )
