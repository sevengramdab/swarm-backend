"""Swarm Mode — Multiple specialized agents collaborate to solve complex problems."""

import json
import asyncio
from typing import List, Dict, Any, AsyncGenerator
from core.autonomy_engine import AutonomyEngine, AutonomyLevel, SSEEvent
from core.session_store import store
from core.model_router import chat_completion, select_model
from core.token_tracker import tracker as token_tracker
from core.swarm_state import state_manager
from core.tool_executor import execute_tool


AGENT_ROLES = {
    "coder": {
        "name": "Coder",
        "system": "You are Coder, a specialist in writing and modifying code. You produce clean, well-documented code. You prefer practical solutions over clever ones.",
    },
    "researcher": {
        "name": "Researcher",
        "system": "You are Researcher, a specialist in investigating codebases, documentation, and finding relevant information. You read files thoroughly and report findings clearly.",
    },
    "debugger": {
        "name": "Debugger",
        "system": "You are Debugger, a specialist in finding and fixing bugs. You analyze error messages, trace execution flow, and suggest precise fixes.",
    },
    "architect": {
        "name": "Architect",
        "system": "You are Architect, a specialist in system design and planning. You think about trade-offs, scalability, and maintainability before recommending solutions.",
    },
    "tester": {
        "name": "Tester",
        "system": "You are Tester, a specialist in writing tests and validating code. You think about edge cases, coverage, and regression risks.",
    },
    "executor": {
        "name": "Executor",
        "system": "You are the Swarm Executor. You implement plans by writing files and running commands. You are concise and action-oriented.",
    },
}

TOOL_SYSTEM_PROMPT = (
    "You have access to tools: read_file, write_file, list_files, run_command, search_files, web_search. "
    "YOUR JOB: Use these tools to DO the work. Do NOT write essays, explanations, or tutorials. "
    "When you need a tool, output ONLY a JSON block like:\n"
    '```tool\n{"tool": "list_files", "args": {"path": "."}}\n```\n'
    "After each tool result, continue with the NEXT tool or a brief summary. "
    "Be CONCISE. One sentence per finding. No fluff. No markdown essays."
)


class SwarmOrchestrator:
    """Orchestrates multiple agents working together with autonomy-aware gates."""

    def __init__(self, max_agents: int = 5):
        self.max_agents = max_agents
        self.messages: List[Dict[str, str]] = []

    async def _call_agent(self, role_key: str, user_content: str, model: str | None = None, use_tools: bool = False, session_id: str | None = None, parent_agent_id: str | None = None, max_iterations: int = 5) -> str:
        """Call a single agent and return its full response."""
        if use_tools:
            return await self._call_agent_with_tools(role_key, user_content, model=model, max_iterations=max_iterations, session_id=session_id, parent_agent_id=parent_agent_id)

        messages = [
            {"role": "system", "content": AGENT_ROLES[role_key]["system"]},
            {"role": "user", "content": user_content},
        ]
        llm_model = model or await select_model(prefer_local=True)
        result = ""
        async for chunk in chat_completion(messages, model=llm_model, stream=False):
            result += chunk

        # Dashboard tracking
        if parent_agent_id:
            agent = state_manager.get_agent(parent_agent_id)
            if agent:
                input_chars = sum(len(m.get("content", "")) for m in messages)
                state_manager.add_telemetry(parent_agent_id, int(input_chars / 4), int(len(result) / 4))
                state_manager.append_thought(parent_agent_id, "llm_output", result[:500])
                await state_manager.broadcast_thought(agent.session_id, parent_agent_id, "llm_output", result[:500])
                await state_manager.broadcast_telemetry(agent.session_id, parent_agent_id, agent.telemetry)
        return result

    async def _call_agent_with_tools(self, role_key: str, user_content: str, model: str | None = None, max_iterations: int = 5, session_id: str | None = None, parent_agent_id: str | None = None) -> str:
        """Run a short agent loop with DIRECT tool execution for a subagent."""
        from core.autonomy_engine import ToolResult

        system_prompt = AGENT_ROLES[role_key]["system"] + "\n\n" + TOOL_SYSTEM_PROMPT
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        full_response = ""
        tool_results = []

        # Dashboard tracking
        dashboard_agent = None
        if parent_agent_id:
            dashboard_agent = state_manager.get_agent(parent_agent_id)
            if dashboard_agent:
                state_manager.update_agent_status(parent_agent_id, "active")
                await state_manager.broadcast_agent_update(dashboard_agent.session_id, parent_agent_id)

        for iteration in range(max_iterations):
            llm_model = model or await select_model(prefer_local=True)
            response = ""
            async for chunk in chat_completion(messages, model=llm_model, stream=False):
                response += chunk

            full_response += f"\n[Iteration {iteration + 1}]\n{response}\n"

            if dashboard_agent:
                input_chars = sum(len(m.get("content", "")) for m in messages)
                state_manager.add_telemetry(parent_agent_id, int(input_chars / 4), int(len(response) / 4))
                state_manager.append_thought(parent_agent_id, "llm_output", response[:500])
                await state_manager.broadcast_thought(dashboard_agent.session_id, parent_agent_id, "llm_output", response[:500])
                await state_manager.broadcast_telemetry(dashboard_agent.session_id, parent_agent_id, dashboard_agent.telemetry)

            tool_calls = AutonomyEngine._extract_tool_calls(response)

            if not tool_calls:
                break

            messages.append({"role": "assistant", "content": response})

            for tc in tool_calls:
                tool_name = tc.get("tool", "")
                args = tc.get("args", {})
                request_id = f"sub-{role_key}-{iteration}-{tool_name}"

                task_item = None
                if dashboard_agent:
                    task_item = state_manager.add_task(parent_agent_id, f"Execute {tool_name}")
                    if task_item:
                        await state_manager.broadcast_task_update(dashboard_agent.session_id, parent_agent_id, task_item)

                # ── DIRECT TOOL EXECUTION (no extension delegation) ──
                raw_result = execute_tool(tool_name, args)
                result = ToolResult(
                    tool=tool_name,
                    args=args,
                    status=raw_result["status"],
                    data=raw_result.get("data"),
                    error=raw_result.get("error", ""),
                )

                tool_results.append(result.to_dict())
                messages.append({"role": "user", "content": f"Tool result: {json.dumps(result.to_dict())}"})

                if dashboard_agent and task_item:
                    progress = 100.0 if result.status in ("ok", "success") else 50.0
                    state_manager.update_task(parent_agent_id, task_item.task_id, "committed", progress)
                    await state_manager.broadcast_task_update(dashboard_agent.session_id, parent_agent_id, task_item)

        if dashboard_agent:
            state_manager.update_agent_status(parent_agent_id, "committed")
            await state_manager.broadcast_agent_update(dashboard_agent.session_id, parent_agent_id)
            await state_manager.broadcast_circuit(dashboard_agent.session_id)

        summary = full_response
        if tool_results:
            summary += "\n\n[Tool Results]\n" + json.dumps(tool_results, indent=2)
        return summary

    async def run(
        self,
        task: str,
        workspace_context: str = "",
        autonomy_level: str = "default",
        batch_mode: bool = True,
        temperature: float | None = None,
        model: str | None = None,
        orchestrator_model: str | None = None,
        subagent_mode: str | None = None,
        session_id: str | None = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Run the swarm on a task with concurrent agents where possible."""
        engine = AutonomyEngine(
            autonomy_level=AutonomyLevel(autonomy_level),
            batch_mode=batch_mode,
            temperature=temperature,
            model=model,
            orchestrator_model=orchestrator_model,
            subagent_mode=subagent_mode,
            session_id=session_id,
        )
        engine.wait_for_approval = store.wait_for_approval
        engine.wait_for_tool_result = store.wait_for_tool_result
        engine.wait_for_decision = store.wait_for_decision
        engine.get_steering = store.pop_steering

        store.create(engine.session_id, autonomy_level)

        self._engine = engine
        async for event in engine.run_swarm_path(
            task=task,
            workspace_context=workspace_context,
            call_agent_fn=lambda role, content, use_tools=False, parent_agent_id=None: self._call_agent(
                role, content,
                model=orchestrator_model or model,
                use_tools=use_tools,
                session_id=engine.session_id,
                parent_agent_id=parent_agent_id,
                max_iterations=2,
            ),
        ):
            yield event


async def swarm_run(
    task: str,
    workspace_context: str = "",
    autonomy_level: str = "default",
    batch_mode: bool = True,
    temperature: float | None = None,
    model: str | None = None,
    orchestrator_model: str | None = None,
    subagent_mode: str | None = None,
    session_id: str | None = None,
) -> AsyncGenerator[SSEEvent, None]:
    """Run the full agent swarm on a task."""
    orchestrator = SwarmOrchestrator()
    async for event in orchestrator.run(
        task,
        workspace_context,
        autonomy_level=autonomy_level,
        batch_mode=batch_mode,
        temperature=temperature,
        model=model,
        orchestrator_model=orchestrator_model,
        subagent_mode=subagent_mode,
        session_id=session_id,
    ):
        yield event
