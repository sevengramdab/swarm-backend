"""
Base Provider Module - The main breaker panel for our cloud power grid.
"""

from __future__ import annotations

import abc
from typing import Any, AsyncIterator, Dict, List, Optional

from pydantic import BaseModel, Field


class InferenceRequest(BaseModel):
    """
    Like a work order you tape to the fridge telling the smart home what to do.
    """
    prompt: str = Field(..., description="The message we want the cloud brain to read.")
    model: Optional[str] = Field(default=None, description="Which appliance model to use.")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="How creative the response should be, like a dimmer switch.")
    max_tokens: Optional[int] = Field(default=1024, description="Max watts before we trip the breaker.")
    tools: Optional[List[Dict[str, Any]]] = Field(default=None, description="Extra gadgets the brain can flip on.")
    images: Optional[List[str]] = Field(default=None, description="Photos we slide under the door for the brain to look at.")
    extra_params: Dict[str, Any] = Field(default_factory=dict, description="Misc knobs and dials.")


class InferenceResponse(BaseModel):
    """
    Like the receipt the smart meter prints after doing the work.
    """
    text: str = Field(..., description="The actual words the cloud brain sent back.")
    model: str = Field(..., description="Which appliance actually did the job.")
    provider: str = Field(..., description="Which power company supplied the juice.")
    usage: Dict[str, int] = Field(default_factory=dict, description="How many kilowatt-tokens we burned.")
    finish_reason: Optional[str] = Field(default=None, description="Why the appliance shut off.")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(default=None, description="Any gadgets the brain decided to flip.")


class ProviderConfig(BaseModel):
    """
    Like the settings on your thermostat: who to call, how much budget, and the secret password.
    """
    name: str = Field(..., description="Name on the mailbox, e.g. 'openai'.")
    api_key: str = Field(..., description="The secret key to unlock the front door.")
    base_url: Optional[str] = Field(default=None, description="Custom address if we aren't using the main power station.")
    default_model: str = Field(..., description="The default appliance model to flip on.")
    timeout: float = Field(default=60.0, description="How many seconds before we assume the lights went out.")
    max_retries: int = Field(default=3, description="How many times we jiggle the handle before giving up.")
    budget_limit: Optional[float] = Field(default=None, description="Max dollars on the electricity bill this month.")


class ProviderError(Exception):
    """
    The whole house lost power because something blew.
    """
    pass


class RateLimitError(ProviderError):
    """
    The power company said 'Whoa, too many requests!' and flipped the breaker.
    """
    pass


class BudgetExceededError(ProviderError):
    """
    We opened the bill and screamed because we already spent the budget.
    """
    pass


class AuthenticationError(ProviderError):
    """
    We typed the garage-door code wrong and got locked out.
    """
    pass


class BaseProvider(abc.ABC):
    """
    The abstract blueprint every power-company connector must follow.
    Think of it as the universal remote that works with any TV brand.
    """

    def __init__(self, config: ProviderConfig, http_client: Optional[Any] = None) -> None:
        """
        Plug the universal remote into the wall and set the channel.

        Args:
            config: The thermostat settings for this provider.
            http_client: A pre-built extension cord; if None we'll buy a new one.
        """
        self.config = config
        self._client = http_client

    @abc.abstractmethod
    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        """
        Push the big red button and ask the cloud brain to think.

        Args:
            request: The work order taped to the fridge.

        Returns:
            The receipt from the smart meter.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def stream_generate(self, request: InferenceRequest) -> AsyncIterator[str]:
        """
        Turn on the faucet and let the words drip out one drop at a time.

        Args:
            request: The work order taped to the fridge.

        Yields:
            Little drips of text as they arrive.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def health_check(self) -> bool:
        """
        Walk over to the breaker panel and make sure the green light is on.

        Returns:
            True if the lights are on, False if we're sitting in the dark.
        """
        raise NotImplementedError
