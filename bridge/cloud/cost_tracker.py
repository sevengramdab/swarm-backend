"""
Cost Tracker - The smart electric meter that watches every kilowatt-token and yells if the bill gets too high.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, PrivateAttr


class ModelPricing(BaseModel):
    """
    The price tag hanging on each appliance in the store.
    """
    prompt_token_cost: float = Field(
        ...,
        description="Dollars per thousand prompt tokens, like the rate per kilowatt-hour."
    )
    completion_token_cost: float = Field(
        ...,
        description="Dollars per thousand completion tokens, like the delivery fee."
    )


class CostTracker(BaseModel):
    """
    A little accountant robot that sits by the breaker panel with a clipboard.
    """
    daily_budget: Optional[float] = Field(
        default=None,
        description="The max dollars we're allowed to spend before the robot pulls the plug."
    )
    model_prices: Dict[str, ModelPricing] = Field(
        default_factory=dict,
        description="The price list for every appliance model."
    )

    _lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)
    _daily_spend: float = PrivateAttr(default=0.0)
    _usage_log: list = PrivateAttr(default_factory=list)

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **data: Any) -> None:
        """
        Wind up the accountant robot and hand it a price sheet.

        Args:
            **data: The configuration knobs for the robot.
        """
        super().__init__(**data)

    async def record_usage(self, provider: str, model: str, usage: Dict[str, int]) -> float:
        """
        Every time an appliance runs, the robot writes down how much power it used and adds it to the bill.

        Args:
            provider: Which power company sold the juice.
            model: Which exact appliance was running.
            usage: The meter reading with prompt and completion tokens.

        Returns:
            The cost of this single run, like the price of one load of laundry.

        Raises:
            BudgetExceededError: If adding this bill would blow the fuse on our budget.
        """
        cost = self.calculate_cost(model, usage)
        async with self._lock:
            if self.daily_budget is not None and self._daily_spend + cost > self.daily_budget:
                from providers.base import BudgetExceededError
                raise BudgetExceededError(
                    f"Whoa there! This load of laundry costs ${cost:.4f}, but we only have "
                    f"${self.daily_budget - self._daily_spend:.4f} left in the piggy bank."
                )
            self._daily_spend += cost
            self._usage_log.append({
                "timestamp": datetime.utcnow().isoformat(),
                "provider": provider,
                "model": model,
                "usage": usage,
                "cost": cost,
            })
        return cost

    def calculate_cost(self, model: str, usage: Dict[str, int]) -> float:
        """
        Multiply the kilowatt-tokens by the price-per-token like a pocket calculator.

        Args:
            model: Which appliance model ran.
            usage: The meter reading dictionary.

        Returns:
            The total dollars owed for this spin cycle.
        """
        pricing = self.model_prices.get(model)
        if pricing is None:
            return 0.0
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        prompt_cost = (prompt_tokens / 1000.0) * pricing.prompt_token_cost
        completion_cost = (completion_tokens / 1000.0) * pricing.completion_token_cost
        return prompt_cost + completion_cost

    async def reset_budget(self) -> None:
        """
        The piggy bank has a daily reset button; press it at midnight.
        """
        async with self._lock:
            self._daily_spend = 0.0
            self._usage_log.clear()

    def get_daily_spend(self) -> float:
        """
        Peek at the piggy bank to see how many coins are left.

        Returns:
            The total dollars spent today.
        """
        return self._daily_spend

    def get_usage_log(self) -> list:
        """
        Flip through the accountant's notebook.

        Returns:
            A list of every transaction today.
        """
        return self._usage_log.copy()
