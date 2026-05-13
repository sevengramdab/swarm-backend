"""Plan Mode — The LLM thinks step-by-step before executing.
Breaks down complex tasks into actionable steps, then optionally executes them."""

import json
from typing import List, Dict, Any, AsyncGenerator
from core.model_router import chat_completion, select_model


SYSTEM_PROMPT = """You are OrbitScribe's Plan Mode assistant. Your job is to analyze the user's request and create a detailed step-by-step implementation plan.

## How You Work
1. **REASON**: Briefly analyze the request and identify the key components
2. **PLAN**: Break the task into clear, sequential, actionable steps
3. **FORMAT**: Present the plan in a structured format

## Output Format
```
## Reasoning
[1-2 sentences on approach and trade-offs]

## Plan
1. **[Step Name]**: Description
2. **[Step Name]**: Description
...

## Dependencies
- Step X depends on Step Y

## Checkpoints
- Steps requiring user confirmation
```

## Rules
- Each step must be specific and actionable
- Identify dependencies between steps
- Flag steps that require user input
- If workspace context is provided, tailor the plan to the actual codebase
- After presenting the plan, ask: "Should I execute this plan?"
- When executing, use tools via ```tool JSON blocks like swarm mode"""


async def plan(
    request: str,
    workspace_context: str = "",
    auto_execute: bool = False,
    stream: bool = True,
    temperature: float | None = None,
    model: str | None = None,
) -> AsyncGenerator[str, None]:
    """Create a step-by-step plan for the user's request."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    if workspace_context:
        messages.append({
            "role": "system",
            "content": f"Current workspace context:\n{workspace_context}",
        })
    
    prompt = f"""Please create a detailed step-by-step plan for this request:

{request}

Format your response as:
1. **Overview**: Brief summary of the approach
2. **Steps**: Numbered list of specific, actionable steps
3. **Dependencies**: Which steps depend on others
4. **User Checkpoints**: Steps that need user input

{'If the user has already approved, proceed to execute the plan after presenting it.' if auto_execute else 'After presenting the plan, ask: "Should I execute this plan?"'}"""
    
    messages.append({"role": "user", "content": prompt})
    
    selected = model or await select_model(prefer_local=True)
    async for chunk in chat_completion(messages, model=selected, stream=stream, temperature=temperature):
        yield chunk


async def execute_step(
    step_description: str,
    step_number: int,
    total_steps: int,
    workspace_context: str = "",
    stream: bool = True,
    temperature: float | None = None,
    model: str | None = None,
) -> AsyncGenerator[str, None]:
    """Execute a single step from a plan."""
    system = f"""You are executing step {step_number} of {total_steps} from a plan.
Execute this step precisely. If you need to write code, provide the full code block.
If you need to run a command, specify the exact command."""
    
    messages = [{"role": "system", "content": system}]
    
    if workspace_context:
        messages.append({
            "role": "system",
            "content": f"Workspace context:\n{workspace_context}",
        })
    
    messages.append({"role": "user", "content": f"Execute this step:\n\n{step_description}"})
    
    selected = model or await select_model(prefer_local=True)
    async for chunk in chat_completion(messages, model=selected, stream=stream, temperature=temperature):
        yield chunk
