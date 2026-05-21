#!/usr/bin/env python3
"""
complexity_scorer.py
====================
Task complexity estimation.

ELI5 Analogy:
  Before an electrician runs a new circuit, they estimate the load:
  how many outlets, what wattage, will it need a dedicated 20A
  breaker or can it share a 15A? ComplexityScorer does the same
  for AI tasks — it counts the "outlets" (prompt tokens), checks
  the "wattage" (model requirements), and decides if the home
  panel can handle it or if the utility company needs to get involved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from pydantic import BaseModel, Field


class ComplexityScore(BaseModel):
    """The electrical load estimate for a single task."""

    overall: float = Field(ge=0.0, le=1.0, default=0.0)
    token_factor: float = Field(ge=0.0, le=1.0, default=0.0)
    capability_factor: float = Field(ge=0.0, le=1.0, default=0.0)
    output_factor: float = Field(ge=0.0, le=1.0, default=0.0)
    multi_modal_factor: float = Field(ge=0.0, le=1.0, default=0.0)
    reasoning_factor: float = Field(ge=0.0, le=1.0, default=0.0)
    tier_recommendation: str = "local"  # local | shadow | cloud


class InferenceRequest(BaseModel):
    """A work order submitted to the electrical panel."""

    prompt: str
    model_hint: Optional[str] = None
    expected_output_tokens: int = 256
    image_attachments: int = 0
    audio_attachments: int = 0
    requires_reasoning: bool = False
    requires_tools: bool = False
    latency_sensitive: bool = False
    cost_sensitive: bool = True


class ComplexityScorer:
    """
    The load calculation sheet.

    ELI5: The master electrician looks at the blueprints and counts:
          - How many rooms need power? (prompt length → tokens)
          - Are we running a microwave or a nightlight? (model capability)
          - Is this a normal outlet or a 240V dryer plug? (output size)
          - Any special circuits? (multi-modal, reasoning depth)
          Then they check the NEC chart and say: "This needs a 20A
          dedicated breaker — your 15A kitchen circuit won't cut it."
    """

    # Approximate tokens per word (rough heuristic).
    TOKENS_PER_WORD: float = 1.3

    # Complexity thresholds — like wire gauge ampacity tables.
    LOCAL_TOKEN_MAX: int = 2_000
    CLOUD_TOKEN_MIN: int = 8_000

    def score(self, request: InferenceRequest) -> ComplexityScore:
        """Run the full load calculation and return the estimate."""
        token_factor = self._score_tokens(request.prompt)
        capability_factor = self._score_capabilities(request)
        output_factor = self._score_output_size(request.expected_output_tokens)
        multi_modal_factor = self._score_multi_modal(request)
        reasoning_factor = self._score_reasoning(request)

        # Weighted average — like combining loads on a panel schedule.
        overall = (
            token_factor * 0.25
            + capability_factor * 0.25
            + output_factor * 0.20
            + multi_modal_factor * 0.15
            + reasoning_factor * 0.15
        )

        tier = self._recommend_tier(overall, request)

        return ComplexityScore(
            overall=round(overall, 3),
            token_factor=round(token_factor, 3),
            capability_factor=round(capability_factor, 3),
            output_factor=round(output_factor, 3),
            multi_modal_factor=round(multi_modal_factor, 3),
            reasoning_factor=round(reasoning_factor, 3),
            tier_recommendation=tier,
        )

    def _score_tokens(self, prompt: str) -> float:
        """
        ELI5: Count the outlets. A 10-word prompt is one outlet.
              A 10,000-word legal brief is a whole apartment building.
        """
        words = len(prompt.split())
        tokens = words * self.TOKENS_PER_WORD
        if tokens <= self.LOCAL_TOKEN_MAX:
            return tokens / self.LOCAL_TOKEN_MAX * 0.5
        if tokens >= self.CLOUD_TOKEN_MIN:
            return 0.5 + (tokens - self.CLOUD_TOKEN_MIN) / self.CLOUD_TOKEN_MIN * 0.5
        # Linear interpolation between local and cloud thresholds.
        return 0.5 + (tokens - self.LOCAL_TOKEN_MAX) / (self.CLOUD_TOKEN_MIN - self.LOCAL_TOKEN_MAX) * 0.5

    def _score_capabilities(self, request: InferenceRequest) -> float:
        """
        ELI5: Are we running a toaster (simple chat) or an arc welder
              (frontier reasoning model)? Check the nameplate rating.
        """
        hint = (request.model_hint or "").lower()
        score = 0.0
        # Frontier-model nameplate checks.
        frontier_markers = ["claude-3-opus", "gpt-4", "gemini-pro", "frontier"]
        if any(m in hint for m in frontier_markers):
            score += 0.6
        # Tool use is like needing a 240V circuit.
        if request.requires_tools:
            score += 0.3
        # Latency-sensitive tasks prefer local (low score).
        if request.latency_sensitive:
            score -= 0.2
        return max(0.0, min(1.0, score))

    def _score_output_size(self, expected_tokens: int) -> float:
        """
        ELI5: A 100-watt bulb draws little. A 5-horsepower motor
              draws a lot. Expected output size is the motor HP rating.
        """
        if expected_tokens <= 256:
            return 0.0
        if expected_tokens >= 4096:
            return 1.0
        return (expected_tokens - 256) / (4096 - 256)

    def _score_multi_modal(self, request: InferenceRequest) -> float:
        """
        ELI5: Text is copper wire — cheap and easy. Images are
              fiber-optic cable — expensive and needs special tools.
        """
        attachments = request.image_attachments + request.audio_attachments
        if attachments == 0:
            return 0.0
        if attachments >= 5:
            return 1.0
        return attachments / 5.0

    def _score_reasoning(self, request: InferenceRequest) -> float:
        """
        ELI5: "Turn on the light" is simple — flip a switch.
              "Design a backup power system for a hospital" needs
              an electrical engineer, code books, and weeks of work.
        """
        score = 0.0
        if request.requires_reasoning:
            score += 0.5
        # Deep reasoning phrases in the prompt.
        reasoning_phrases = [
            "think step by step",
            "reasoning",
            "analyze",
            "compare and contrast",
            "prove",
            "derive",
            "architect",
            "design a system",
        ]
        prompt_lower = request.prompt.lower()
        matches = sum(1 for phrase in reasoning_phrases if phrase in prompt_lower)
        score += min(matches * 0.15, 0.5)
        return min(1.0, score)

    def _recommend_tier(self, overall: float, request: InferenceRequest) -> str:
        """
        ELI5: Look at the total load on the load calculation sheet.
              Under 30% → home solar panels (local).
              30-70% → maybe the grid, maybe solar — check cost (shadow).
              Over 70% → definitely call the utility company (cloud).
        """
        if request.cost_sensitive and overall < 0.35:
            return "local"
        if overall < 0.35:
            return "local"
        if overall < 0.70:
            return "shadow"
        return "cloud"
