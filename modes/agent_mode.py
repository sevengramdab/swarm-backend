"""Agent Mode — Autonomous single agent that can use tools to solve problems."""

import json
from typing import List, Dict, Any, AsyncGenerator
from core.autonomy_engine import AutonomyEngine, AutonomyLevel, SSEEvent
from core.session_store import store
from core.model_router import chat_completion, select_model


SYSTEM_PROMPT = """You are OrbitScribe's Agent Mode. You are an autonomous single-agent coding assistant with direct tool access.

## How You Work
1. **THINK**: Briefly reason about what you need to do and which tool to use
2. **ACT**: Output the tool call in the exact JSON format below
3. **OBSERVE**: The system returns the tool result
4. **REPEAT**: Continue the loop until the task is complete

## Available Tools
When you need a tool, output ONLY a JSON block inside ```tool ... ``` like:
```tool
{"tool": "list_files", "args": {"path": "."}}
```

EXACT tools and their EXACT arguments:
- list_files: args={"path": "<dir>"}
- read_file: args={"path": "<file>"}
- write_file: args={"path": "<file>", "content": "<full content>"}
- run_command: args={"command": "<shell command>"}
- search_files: args={"query": "<search term>", "path": "."}
- web_search: args={"query": "<search term>"}
- calculate: args={"expression": "<math expression>"}
- etsy_profit_calculator: args={"selling_price": 25.00, "product_cost": 8.50, "shipping_cost": 4.99, "quantity": 1, "offsite_ads_rate": 0}
- etsy_research: args={"query": "trending Etsy products 2024", "max_results": 5}
- etsy_pricing_optimizer: args={"product_cost": 8.50, "shipping_cost": 4.99, "target_margin": 40, "competitor_low": 15.00, "competitor_high": 30.00}
- etsy_listing_template: args={"product_name": "Custom Wood Sign", "category": "Home Decor"}

## Rules
- Output ONLY tool JSON blocks when acting. No markdown essays between tool calls.
- After a tool result, output the NEXT tool JSON block immediately.
- When you have the answer, provide a clear final response.
- Be CONCISE in your reasoning. Focus on doing, not explaining."""


class AgentSession:
    """Tracks an agent session with message history and tool results."""
    
    def __init__(self):
        self.messages: List[Dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        self.tool_results: List[Dict[str, Any]] = []
    
    async def run(
        self,
        task: str,
        workspace_context: str = "",
        max_iterations: int = 10,
        autonomy_level: str = "default",
        batch_mode: bool = True,
        temperature: float | None = None,
        model: str | None = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Run the agent on a task, yielding structured SSE events."""
        if workspace_context:
            self.messages.append({
                "role": "system",
                "content": f"Workspace context:\n{workspace_context}",
            })
        
        self.messages.append({"role": "user", "content": task})
        
        engine = AutonomyEngine(
            autonomy_level=AutonomyLevel(autonomy_level),
            max_iterations=max_iterations,
            batch_mode=batch_mode,
            temperature=temperature,
            model=model,
        )
        
        # Wire session store hooks
        engine.wait_for_approval = store.wait_for_approval
        engine.wait_for_tool_result = store.wait_for_tool_result
        engine.wait_for_decision = store.wait_for_decision
        engine.get_steering = store.pop_steering
        engine.check_stop = store.is_stopped
        
        # Create session in store so the extension can send tool results back
        session = store.create(engine.session_id, autonomy_level)
        # Sync the store session's message list with the agent's so compact works
        session.messages = self.messages
        
        try:
            async for event in engine.run_agent_loop(
                messages=self.messages,
                system_prompt=SYSTEM_PROMPT,
                workspace_context=workspace_context,
            ):
                yield event
        finally:
            # Keep session around briefly for any late tool results, but mark for cleanup
            pass


async def agent_run(
    task: str,
    workspace_context: str = "",
    stream: bool = True,
    autonomy_level: str = "default",
    batch_mode: bool = True,
    temperature: float | None = None,
    model: str | None = None,
) -> AsyncGenerator[SSEEvent, None]:
    """Run a single agent on a task."""
    session = AgentSession()
    async for event in session.run(task, workspace_context, autonomy_level=autonomy_level, batch_mode=batch_mode, temperature=temperature, model=model):
        yield event
