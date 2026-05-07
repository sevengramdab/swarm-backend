"""Agent Mode — Autonomous single agent that can use tools to solve problems."""

import json
from typing import List, Dict, Any, AsyncGenerator
from core.autonomy_engine import AutonomyEngine, AutonomyLevel, SSEEvent
from core.session_store import store
from core.model_router import chat_completion, select_model


SYSTEM_PROMPT = """You are OrbitScribe's Agent Mode. You are an autonomous coding assistant with tool access.

Available tools:
- read_file(path): Read a file's contents
- write_file(path, content): Write content to a file
- list_files(path): List files in a directory
- run_command(command): Run a shell command
- search_files(query): Search for files matching a query
- get_current_weather(location): Get current weather for a location (e.g., 'Seattle')
- get_time_at_location(location): Get current local time for a location

When you need to use a tool, output a JSON block like:
```tool
{"tool": "read_file", "args": {"path": "src/main.py"}}
```

The system will execute the tool and return the result. Continue until the task is complete.
Always explain what you're doing before using a tool."""


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
