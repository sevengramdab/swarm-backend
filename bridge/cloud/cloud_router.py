"""
Cloud Router - The master breaker panel that decides which power line to use.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional

from pydantic import BaseModel, Field

from providers.base import (
    BaseProvider,
    InferenceRequest,
    InferenceResponse,
    ProviderError,
    RateLimitError,
    BudgetExceededError,
)
from cost_tracker import CostTracker


class CloudRouter(BaseModel):
    """
    The big red lever on the wall that flips between city power, solar, and backup generator.
    """
    cost_tracker: CostTracker = Field(..., description="The accountant robot tracking the bill.")
    providers: Dict[str, BaseProvider] = Field(default_factory=dict, description="All the extension cords plugged into the wall.")
    tier_map: Dict[str, List[str]] = Field(default_factory=dict, description="Which outlets belong to which priority tier.")
    fallback_enabled: bool = Field(default=True, description="Whether we try the next outlet if the first one trips.")

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **data: Any) -> None:
        """
        Install the master breaker panel and label every switch.

        Args:
            **data: The wiring schematic for the whole house.
        """
        super().__init__(**data)

    async def route_request(self, request: InferenceRequest, tier: str) -> InferenceResponse:
        """
        Look at the tier label and flip the best switch to power the cloud brain.

        Args:
            request: The work order taped to the fridge.
            tier: Which speed dial to use - 'fast', 'balanced', or 'frontier'.

        Returns:
            The receipt from whichever appliance actually did the work.

        Raises:
            ProviderError: If every single breaker trips and the house goes dark.
        """
        provider_names = self.tier_map.get(tier)
        if not provider_names:
            provider_names = list(self.providers.keys())

        last_error: Optional[Exception] = None
        for name in provider_names:
            provider = self.providers.get(name)
            if provider is None:
                continue
            try:
                response = await provider.generate(request)
                await self.cost_tracker.record_usage(response.provider, response.model, response.usage)
                return response
            except BudgetExceededError:
                raise
            except RateLimitError as e:
                last_error = e
                if self.fallback_enabled:
                    continue
                raise
            except ProviderError as e:
                last_error = e
                if self.fallback_enabled:
                    continue
                raise

        raise ProviderError(f"All breakers tripped for tier '{tier}'. Last spark: {last_error}")

    async def stream_route(self, request: InferenceRequest, tier: str) -> AsyncIterator[str]:
        """
        Same as route_request, but open the faucet so words drip out live.

        Args:
            request: The work order taped to the fridge.
            tier: Which speed dial to use.

        Yields:
            Each drip of text as it arrives from the chosen outlet.
        """
        provider_names = self.tier_map.get(tier)
        if not provider_names:
            provider_names = list(self.providers.keys())

        last_error: Optional[Exception] = None
        for name in provider_names:
            provider = self.providers.get(name)
            if provider is None:
                continue
            try:
                async for chunk in provider.stream_generate(request):
                    yield chunk
                return
            except BudgetExceededError:
                raise
            except RateLimitError as e:
                last_error = e
                if self.fallback_enabled:
                    continue
                raise
            except ProviderError as e:
                last_error = e
                if self.fallback_enabled:
                    continue
                raise

        raise ProviderError(f"All faucets dried up for tier '{tier}'. Last drip error: {last_error}")

    def register_provider(self, name: str, provider: BaseProvider) -> None:
        """
        Screw a new extension cord into the master panel and label it.

        Args:
            name: The label for the new switch.
            provider: The cord itself.
        """
        self.providers[name] = provider

    def set_tier_map(self, tier: str, provider_names: List[str]) -> None:
        """
        Decide which outlets the 'fast', 'balanced', and 'frontier' sticky notes point to.

        Args:
            tier: The sticky note color.
            provider_names: The ordered list of switches to try.
        """
        self.tier_map[tier] = provider_names

    async def health_check_all(self) -> Dict[str, bool]:
        """
        Walk around the house and flip every light switch to see if the bulbs work.

        Returns:
            A map of switch labels to True (lit) or False (dark).
        """
        results: Dict[str, bool] = {}
        for name, provider in self.providers.items():
            try:
                results[name] = await provider.health_check()
            except Exception:
                results[name] = False
        return results
