"""Agent Mode — Autonomous single agent that can use tools to solve problems."""

import json
from typing import List, Dict, Any, AsyncGenerator
from core.model_router import chat_completion, select_model


SYSTEM_PROMPT = """You are OrbitScribe's Agent Mode. You are an autonomous coding assistant with tool access.

Available tools:
- read_file(path): Read a file's contents
- write_file(path, content): Write content to a file
- list_files(path): List files in a directory
- run_command(command): Run a shell command
- search_files(query): Search for files matching a query

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
    ) -> AsyncGenerator[str, None]:
        """Run the agent on a task, yielding text and tool calls."""
        if workspace_context:
            self.messages.append({
                "role": "system",
                "content": f"Workspace context:\n{workspace_context}",
            })
        
        self.messages.append({"role": "user", "content": task})
        
        for iteration in range(max_iterations):
            model = await select_model(prefer_local=True)
            full_response = ""
            
            async for chunk in chat_completion(self.messages, model=model, stream=False):
                full_response += chunk
            
            # Check for tool calls
            tool_calls = self._extract_tool_calls(full_response)
            
            if tool_calls:
                self.messages.append({"role": "assistant", "content": full_response})
                yield full_response
                
                for tool_call in tool_calls:
                    yield f"\n[TOOL: {tool_call['tool']}]\n"
                    result = await self._execute_tool(tool_call)
                    yield f"[RESULT]: {json.dumps(result, indent=2)}\n"
                    self.messages.append({
                        "role": "user",
                        "content": f"Tool result: {json.dumps(result)}",
                    })
            else:
                self.messages.append({"role": "assistant", "content": full_response})
                yield full_response
                break
        else:
            yield "\n[Agent reached maximum iterations. Task may be incomplete.]"
    
    def _extract_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """Extract tool calls from assistant response."""
        tools = []
        if "```tool" in text:
            parts = text.split("```tool")
            for part in parts[1:]:
                code = part.split("```")[0].strip()
                try:
                    tools.append(json.loads(code))
                except json.JSONDecodeError:
                    pass
        return tools
    
    async def _execute_tool(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool call. Placeholder — real implementation in extension bridge."""
        tool_name = tool_call.get("tool", "")
        args = tool_call.get("args", {})
        
        # These will be handled by the VS Code extension
        return {
            "tool": tool_name,
            "args": args,
            "status": "pending",
            "note": "Tool execution delegated to VS Code extension",
        }


async def agent_run(
    task: str,
    workspace_context: str = "",
    stream: bool = True,
) -> AsyncGenerator[str, None]:
    """Run a single agent on a task."""
    session = AgentSession()
    async for chunk in session.run(task, workspace_context):
        yield chunk
