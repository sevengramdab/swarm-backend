"""
Google Gemini Connector - The smart thermostat that chats with Google's solar farm.
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


class GoogleConfig(ProviderConfig):
    """
    The wiring diagram specific to Google's power station.
    """
    project_id: Optional[str] = Field(default=None, description="Which neighborhood grid we're tapping into.")
    location: str = Field(default="us-central1", description="Which transformer box on the street.")
    api_version: str = Field(default="v1beta", description="Which edition of the manual we're reading.")


class GoogleConnector(BaseProvider):
    """
    A universal adapter that plugs our house into Google's massive solar array.
    """

    def __init__(self, config: GoogleConfig, http_client: Optional[httpx.AsyncClient] = None) -> None:
        """
        Screw the Google adapter into the wall socket.

        Args:
            config: The solar-panel settings sheet.
            http_client: A spare power cord, or None to unwrap a new one.
        """
        super().__init__(config, http_client)
        self.config: GoogleConfig = config
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "Content-Type": "application/json",
                },
                timeout=config.timeout,
                base_url=config.base_url or self._default_base_url(),
            )

    def _default_base_url(self) -> str:
        """
        Look up the street address of the nearest Google transformer.

        Returns:
            The URL where we mail our request.
        """
        base = "https://generativelanguage.googleapis.com"
        return f"{base}/{self.config.api_version}"

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        """
        Push the Google doorbell and show them our photo album while asking a question.

        Args:
            request: The postcard with optional pictures glued to the back.

        Returns:
            The Polaroid Google snaps and sends back.
        """
        payload = self._build_payload(request)
        model = request.model or self.config.default_model
        endpoint = f"models/{model}:generateContent?key={self.config.api_key}"
        response = await self._client.post(endpoint, json=payload)
        await self._raise_for_status(response)
        data = response.json()
        return self._parse_response(data)

    async def stream_generate(self, request: InferenceRequest) -> AsyncIterator[str]:
        """
        Open the Google drinking fountain so each word bubbles up one sip at a time.

        Args:
            request: The postcard with optional pictures glued to the back.

        Yields:
            Each sip of text as it rises to the surface.
        """
        payload = self._build_payload(request)
        model = request.model or self.config.default_model
        endpoint = f"models/{model}:streamGenerateContent?key={self.config.api_key}"
        async with self._client.stream("POST", endpoint, json=payload) as response:
            await self._raise_for_status(response)
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    candidates = chunk.get("candidates", [])
                    for candidate in candidates:
                        parts = candidate.get("content", {}).get("parts", [])
                        for part in parts:
                            text = part.get("text", "")
                            if text:
                                yield text
                except json.JSONDecodeError:
                    continue

    async def health_check(self) -> bool:
        """
        Ping the Google solar farm to see if the panels are still catching rays.

        Returns:
            True if the voltmeter reads green, False if the panels are asleep.
        """
        try:
            endpoint = f"models?key={self.config.api_key}&pageSize=1"
            response = await self._client.get(endpoint)
            return response.status_code == 200
        except Exception:
            return False

    def _build_payload(self, request: InferenceRequest) -> Dict[str, Any]:
        """
        Pack our lunchbox exactly the way the Google cafeteria expects.

        Args:
            request: The raw groceries we want to send.

        Returns:
            A neatly organized bento box.
        """
        parts: List[Dict[str, Any]] = [{"text": request.prompt}]
        if request.images:
            for img in request.images:
                parts.append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": img,
                    }
                })
        contents: List[Dict[str, Any]] = [{"role": "user", "parts": parts}]
        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
            },
        }
        if request.max_tokens is not None:
            payload["generationConfig"]["maxOutputTokens"] = request.max_tokens
        if request.tools:
            payload["tools"] = [{"function_declarations": request.tools}]
        if request.extra_params:
            payload.update(request.extra_params)
        return payload

    async def _raise_for_status(self, response: httpx.Response) -> None:
        """
        Inspect the package from the Google delivery truck for damage.

        Args:
            response: The cardboard box on the doorstep.

        Raises:
            RateLimitError: If Google ran out of stamps.
            AuthenticationError: If the delivery driver doesn't trust us.
            ProviderError: If the truck crashed into a tree.
        """
        if response.status_code == 200:
            return
        if response.status_code == 429:
            raise RateLimitError("Google's meter is spinning too fast: rate limit.")
        if response.status_code in (401, 403):
            raise AuthenticationError("Google's gate code changed: bad key.")
        try:
            body = response.json()
            message = body.get("error", {}).get("message", "Unknown Google error")
        except Exception:
            message = response.text or "Unknown Google error"
        raise ProviderError(f"Google's transformer blew ({response.status_code}): {message}")

    def _parse_response(self, data: Dict[str, Any]) -> InferenceResponse:
        """
        Unpack the crate Google shipped back and inventory the contents.

        Args:
            data: The wooden crate full of words.

        Returns:
            A neatly typed invoice of what we received.
        """
        candidates = data.get("candidates", [])
        text_parts: List[str] = []
        tool_calls: Optional[List[Dict[str, Any]]] = None
        for candidate in candidates:
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                if "text" in part:
                    text_parts.append(part["text"])
                if "functionCall" in part:
                    if tool_calls is None:
                        tool_calls = []
                    tool_calls.append({
                        "name": part["functionCall"].get("name"),
                        "arguments": part["functionCall"].get("args"),
                    })
        usage = data.get("usageMetadata", {})
        return InferenceResponse(
            text="\n".join(text_parts),
            model=self.config.default_model,
            provider="google",
            usage={
                "prompt_tokens": usage.get("promptTokenCount", 0),
                "completion_tokens": usage.get("candidatesTokenCount", 0),
                "total_tokens": usage.get("totalTokenCount", 0),
            },
            finish_reason=candidates[0].get("finishReason") if candidates else None,
            tool_calls=tool_calls,
        )
