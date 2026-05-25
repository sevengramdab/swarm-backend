"""
plan_creator.py
===============
Interactive planning for SwarmCoder.

ELI5: Instead of the agent immediately building something,
      it first sketches 3 different blueprints and asks you
      which one you like before starting construction.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PlanOption:
    option_id: str
    title: str
    description: str
    approach: str
    estimated_files: int
    complexity: str  # low / medium / high
    tools_needed: List[str] = field(default_factory=list)


@dataclass
class CreatedPlan:
    plan_id: str
    goal: str
    options: List[PlanOption]
    created_at: float = field(default_factory=time.time)
    selected_option_id: Optional[str] = None
    status: str = "pending"  # pending / selected / executing / completed / failed
    result_summary: str = ""
    task_id: Optional[str] = None


class PlanCreator:
    """Generates multi-option plans before execution."""

    def __init__(self, llm):
        self.llm = llm
        self._plans: Dict[str, CreatedPlan] = {}

    def create_plan(self, goal: str) -> CreatedPlan:
        """Ask the LLM for 3-4 different approaches to the goal."""
        system = """You are a senior software architect. The user has a goal.
Your job is to sketch 3-4 DIFFERENT approaches to achieve it.

For each approach, provide:
- title: Short name (3-5 words)
- description: What this approach does and why you'd choose it (1-2 sentences)
- approach: Technical strategy (e.g., "Pure Python CLI with argparse", "Streamlit dashboard with SQLite backend")
- estimated_files: Approximate number of files to create (integer)
- complexity: low / medium / high
- tools_needed: List of tools/libraries needed (e.g., ["argparse", "requests", "sqlite3"])

Return ONLY a JSON array. No markdown, no explanations outside the JSON."""

        user = f"Goal: {goal}\n\nSketch 3-4 different approaches. Return ONLY JSON."
        result = self.llm.chat(system, user, temperature=0.4, timeout=90)

        options = []
        if result.get("success"):
            raw = result["response"]
            # Try to extract JSON array
            try:
                start = raw.find("[")
                end = raw.rfind("]")
                if start != -1 and end != -1:
                    data = json.loads(raw[start:end+1], strict=False)
                    for i, item in enumerate(data):
                        options.append(PlanOption(
                            option_id=f"opt-{i+1}",
                            title=item.get("title", f"Option {i+1}"),
                            description=item.get("description", ""),
                            approach=item.get("approach", ""),
                            estimated_files=item.get("estimated_files", 1),
                            complexity=item.get("complexity", "medium"),
                            tools_needed=item.get("tools_needed", []),
                        ))
            except Exception:
                pass

        # Fallback: if parsing failed, create generic options
        if not options:
            options = [
                PlanOption("opt-1", "Minimal Script", "A single-file solution focused on simplicity.", "single_file", 1, "low"),
                PlanOption("opt-2", "Modular Tool", "Split into modules for maintainability.", "modular", 3, "medium"),
                PlanOption("opt-3", "Full Application", "Complete app with config, tests, and docs.", "full_app", 6, "high"),
            ]

        plan = CreatedPlan(
            plan_id=str(uuid.uuid4())[:8],
            goal=goal,
            options=options,
        )
        self._plans[plan.plan_id] = plan
        return plan

    def get_plan(self, plan_id: str) -> Optional[CreatedPlan]:
        return self._plans.get(plan_id)

    def select_option(self, plan_id: str, option_id: str) -> Optional[CreatedPlan]:
        plan = self._plans.get(plan_id)
        if not plan:
            return None
        valid_ids = {o.option_id for o in plan.options}
        if option_id not in valid_ids:
            return None
        plan.selected_option_id = option_id
        plan.status = "selected"
        return plan

    def to_dict(self, plan: CreatedPlan) -> dict:
        return {
            "plan_id": plan.plan_id,
            "goal": plan.goal,
            "status": plan.status,
            "selected_option_id": plan.selected_option_id,
            "task_id": plan.task_id,
            "result_summary": plan.result_summary,
            "options": [
                {
                    "option_id": o.option_id,
                    "title": o.title,
                    "description": o.description,
                    "approach": o.approach,
                    "estimated_files": o.estimated_files,
                    "complexity": o.complexity,
                    "tools_needed": o.tools_needed,
                }
                for o in plan.options
            ],
        }
