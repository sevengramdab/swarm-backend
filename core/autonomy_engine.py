"""
Autonomy Engine — Three-tier permission system for agentic tool execution.

Tiers:
  DEFAULT   : Manual gating. Every tool call requires explicit user approval.
  OVERRIDE  : Bypass approvals. Auto-execute tools, auto-retry on standard errors,
              but pause on subjective ambiguity/decisions.
  AUTOPILOT : Full closed-loop autonomy. Bypass all approvals, auto-retry,
              self-resolve ambiguity with LLM, loop until task_complete.
"""

import asyncio
import json
import logging
import uuid
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional, Callable

from core.model_router import chat_completion, select_model
from core.change_tracker import tracker, ChangeBatch, BatchStatus
from core.token_tracker import tracker as token_tracker
from core.swarm_state import state_manager

logger = logging.getLogger(__name__)


class AutonomyLevel(str, Enum):
    DEFAULT = "default"
    OVERRIDE = "override"
    AUTOPILOT = "autopilot"


class NodeType(str, Enum):
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    APPROVAL_GATE = "approval_gate"
    DECISION_GATE = "decision_gate"
    AUTO_RETRY = "auto_retry"
    SELF_RESOLVE = "self_resolve"
    TASK_COMPLETE = "task_complete"
    PASS_THROUGH = "pass_through"


class ExecutionNode:
    """A node in the Signal Path DAG."""

    def __init__(
        self,
        node_id: str,
        node_type: NodeType,
        config: Dict[str, Any],
        next_on_success: Optional[str] = None,
        next_on_failure: Optional[str] = None,
        next_on_approval: Optional[str] = None,
        next_on_rejection: Optional[str] = None,
    ):
        self.id = node_id
        self.type = node_type
        self.config = config
        self.next_on_success = next_on_success
        self.next_on_failure = next_on_failure
        self.next_on_approval = next_on_approval
        self.next_on_rejection = next_on_rejection


class SignalPath:
    """Directed Acyclic Graph describing an execution flow."""

    def __init__(self):
        self.nodes: Dict[str, ExecutionNode] = {}
        self.start_node: Optional[str] = None

    def add_node(self, node: ExecutionNode) -> "SignalPath":
        self.nodes[node.id] = node
        if self.start_node is None:
            self.start_node = node.id
        return self

    def set_start(self, node_id: str) -> "SignalPath":
        self.start_node = node_id
        return self

    def get_node(self, node_id: str) -> Optional[ExecutionNode]:
        return self.nodes.get(node_id)


class ToolResult:
    def __init__(self, tool: str, args: dict, status: str, data: Any = None, error: str = ""):
        self.tool = tool
        self.args = args
        self.status = status
        self.data = data
        self.error = error

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "args": self.args,
            "status": self.status,
            "data": self.data,
            "error": self.error,
        }


class SSEEvent:
    """Structured Server-Sent Event payload."""

    def __init__(self, event_type: str, payload: Dict[str, Any]):
        self.event_type = event_type
        self.payload = payload

    def to_json(self) -> str:
        return json.dumps({"type": self.event_type, **self.payload})


class AutonomyEngine:
    """
    Executes agent loops while respecting the active AutonomyLevel.
    Yields structured SSEEvents for the frontend to consume.
    """

    def __init__(
        self,
        autonomy_level: AutonomyLevel = AutonomyLevel.DEFAULT,
        session_id: Optional[str] = None,
        max_iterations: int = 10,
        max_retries: int = 2,
        batch_mode: bool = True,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
        orchestrator_model: Optional[str] = None,
        subagent_mode: Optional[str] = None,
    ):
        self.autonomy = autonomy_level
        self.session_id = session_id or str(uuid.uuid4())
        self.max_iterations = max_iterations
        self.max_retries = max_retries
        self.iteration = 0
        self.batch_mode = batch_mode
        self.temperature = temperature
        self.model = model
        self.orchestrator_model = orchestrator_model
        self.subagent_mode = subagent_mode
        self._change_batch: Optional[ChangeBatch] = None
        self._dashboard_agent_id: Optional[str] = None

        # Hooks populated by the session store / routes
        self.wait_for_approval: Optional[Callable[[str, str, dict], asyncio.Future[bool]]] = None
        self.wait_for_tool_result: Optional[Callable[[str, str, dict], asyncio.Future[ToolResult]]] = None
        self.wait_for_decision: Optional[Callable[[str, str, dict], asyncio.Future[str]]] = None
        self.get_steering: Optional[Callable[[str], Optional[str]]] = None
        self.check_stop: Optional[Callable[[str], bool]] = None

    def _track_tokens(self, messages: List[Dict[str, str]], response_text: str):
        """Estimate and track token usage for this LLM call."""
        input_chars = sum(len(m.get("content", "")) for m in messages)
        output_chars = len(response_text)
        input_tok = int(input_chars / 4)
        out_tok = int(output_chars / 4)
        token_tracker.add(
            session_id=self.session_id,
            input_chars=input_chars,
            output_chars=output_chars,
        )
        # Also push to dashboard state manager
        if self._dashboard_agent_id:
            state_manager.add_telemetry(self._dashboard_agent_id, input_tok, out_tok)

    def _emit_token_usage(self) -> SSEEvent:
        """Emit current token usage as an SSE event."""
        return SSEEvent("token_usage", token_tracker.to_dict(self.session_id))

    async def run_agent_loop(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        workspace_context: str = "",
        agent_role: str = "agent",
        agent_name: str = "Agent",
        parent_agent_id: Optional[str] = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Main agent execution loop.
        Yields structured SSE events for the frontend to consume.
        """
        if not messages:
            messages = [{"role": "system", "content": system_prompt}]
            if workspace_context:
                messages.append({"role": "system", "content": f"Workspace context:\n{workspace_context}"})

        # Initialize change batch for this session if batch mode is on
        if self.batch_mode:
            self._change_batch = tracker.create_batch(self.session_id, title="Agent Changes")

        # Register dashboard agent node
        if parent_agent_id:
            agent_node = state_manager.spawn_agent(parent_agent_id, agent_role, agent_name, system_prompt)
        else:
            agent_node = state_manager.spawn_agent(
                state_manager._session_roots.get(self.session_id, ""),
                agent_role, agent_name, system_prompt,
            ) if state_manager._session_roots.get(self.session_id) else None
            if not agent_node:
                # Fallback: create a root for this session if none exists
                agent_node = state_manager.create_swarm(self.session_id, f"Agent mode: {agent_name}")
                agent_node.role = agent_role
                agent_node.name = agent_name
                agent_node.system_prompt = system_prompt
        if agent_node:
            self._dashboard_agent_id = agent_node.agent_id
            state_manager.update_agent_status(self._dashboard_agent_id, "active")
            await state_manager.broadcast_agent_update(self.session_id, self._dashboard_agent_id)

        for iteration in range(self.max_iterations):
            self.iteration = iteration

            # --- Check for stop signal ---
            if self.check_stop and self.check_stop(self.session_id):
                yield SSEEvent("text", {"chunk": "\n[Stopped by user]\n"})
                if self._dashboard_agent_id:
                    state_manager.update_agent_status(self._dashboard_agent_id, "idle")
                    await state_manager.broadcast_agent_update(self.session_id, self._dashboard_agent_id)
                    await state_manager.broadcast_circuit(self.session_id)
                yield SSEEvent("task_complete", {"session_id": self.session_id, "result": "[Stopped by user]", "iterations": iteration})
                return

            # --- Check for steering messages ---
            if self.get_steering:
                steer_msg = self.get_steering(self.session_id)
                if steer_msg:
                    messages.append({"role": "user", "content": f"[STEERING] {steer_msg}"})
                    yield SSEEvent("text", {"chunk": f"\n🎯 Steering: {steer_msg}\n"})
                    if self._dashboard_agent_id:
                        state_manager.append_thought(self._dashboard_agent_id, "steering", steer_msg)
                        await state_manager.broadcast_thought(self.session_id, self._dashboard_agent_id, "steering", steer_msg)

            # --- LLM Call ---
            llm_model = self.model or await select_model(prefer_local=True, subagent_mode=self.subagent_mode)
            full_response = ""
            async for chunk in chat_completion(messages, model=llm_model, stream=False, temperature=self.temperature):
                full_response += chunk

            self._track_tokens(messages, full_response)
            yield SSEEvent("text", {"chunk": full_response})
            yield self._emit_token_usage()
            if self._dashboard_agent_id:
                state_manager.append_thought(self._dashboard_agent_id, "llm_output", full_response)
                await state_manager.broadcast_thought(self.session_id, self._dashboard_agent_id, "llm_output", full_response[:500])

            tool_calls = self._extract_tool_calls(full_response)

            if not tool_calls:
                messages.append({"role": "assistant", "content": full_response})
                batch_event = self._maybe_emit_batch_event()
                if batch_event:
                    yield batch_event
                if self._dashboard_agent_id:
                    state_manager.update_agent_status(self._dashboard_agent_id, "committed")
                    await state_manager.broadcast_agent_update(self.session_id, self._dashboard_agent_id)
                    await state_manager.broadcast_circuit(self.session_id)
                yield SSEEvent("task_complete", {"session_id": self.session_id, "result": full_response, "iterations": iteration + 1})
                return

            messages.append({"role": "assistant", "content": full_response})

            # Process each tool call
            for tc in tool_calls:
                tool_name = tc.get("tool", "")
                args = tc.get("args", {})
                request_id = str(uuid.uuid4())[:8]

                task_item = None
                if self._dashboard_agent_id:
                    task_item = state_manager.add_task(self._dashboard_agent_id, f"Execute {tool_name}")
                    if task_item:
                        await state_manager.broadcast_task_update(self.session_id, self._dashboard_agent_id, task_item)

                # --- Approval Gate ---
                if self.autonomy == AutonomyLevel.DEFAULT:
                    yield SSEEvent("approval_required", {
                        "session_id": self.session_id,
                        "request_id": request_id,
                        "tool": tool_name,
                        "args": args,
                        "message": f"The agent wants to execute `{tool_name}` with args {json.dumps(args)}. Approve?",
                    })
                    approved = False
                    if self.wait_for_approval:
                        try:
                            approved = await asyncio.wait_for(
                                self.wait_for_approval(self.session_id, request_id, {"tool": tool_name, "args": args}),
                                timeout=300.0,
                            )
                        except asyncio.TimeoutError:
                            approved = False
                    if not approved:
                        result = ToolResult(tool_name, args, "blocked", error="Execution blocked by user or timeout")
                        yield SSEEvent("tool_result", {"request_id": request_id, **result.to_dict()})
                        messages.append({"role": "user", "content": f"Tool result (blocked): {json.dumps(result.to_dict())}"})
                        if task_item:
                            state_manager.update_task(self._dashboard_agent_id, task_item.task_id, "committed", 100.0)
                            await state_manager.broadcast_task_update(self.session_id, self._dashboard_agent_id, task_item)
                        continue

                elif self.autonomy == AutonomyLevel.OVERRIDE:
                    yield SSEEvent("tool_request", {
                        "session_id": self.session_id,
                        "request_id": request_id,
                        "tool": tool_name,
                        "args": args,
                        "requires_approval": False,
                        "note": "Auto-executing in OVERRIDE mode",
                    })

                elif self.autonomy == AutonomyLevel.AUTOPILOT:
                    yield SSEEvent("tool_request", {
                        "session_id": self.session_id,
                        "request_id": request_id,
                        "tool": tool_name,
                        "args": args,
                        "requires_approval": False,
                        "note": "Auto-executing in AUTOPILOT mode",
                    })

                # --- Tool Execution with Retry ---
                result = await self._execute_tool_with_retry(request_id, tool_name, args)
                yield SSEEvent("tool_result", {"request_id": request_id, **result.to_dict()})
                messages.append({"role": "user", "content": f"Tool result: {json.dumps(result.to_dict())}"})
                if task_item:
                    progress = 100.0 if result.status in ("ok", "success") else 50.0
                    state_manager.update_task(self._dashboard_agent_id, task_item.task_id, "committed", progress)
                    await state_manager.broadcast_task_update(self.session_id, self._dashboard_agent_id, task_item)

                # --- Track write_file in change batch ---
                if self.batch_mode and tool_name == "write_file" and result.status in ("ok", "success"):
                    original = None
                    if result.data and isinstance(result.data, dict):
                        original = result.data.get("original_content")
                    if self._change_batch:
                        self._change_batch.add_change(
                            file_path=args.get("path", "unknown"),
                            original_content=original,
                            new_content=args.get("content", ""),
                        )

                # --- AUTOPILOT Self-Resolve on Ambiguity ---
                if self.autonomy == AutonomyLevel.AUTOPILOT and result.status == "ambiguous":
                    resolution = await self._self_resolve(messages, result)
                    yield SSEEvent("text", {"chunk": f"[Self-Resolved] {resolution}\n"})
                    messages.append({"role": "user", "content": f"Self-resolution: {resolution}"})
                    if self._dashboard_agent_id:
                        state_manager.append_thought(self._dashboard_agent_id, "self_resolve", resolution)

                # --- OVERRIDE Decision Gate on Ambiguity ---
                if self.autonomy == AutonomyLevel.OVERRIDE and result.status == "ambiguous":
                    yield SSEEvent("decision_required", {
                        "session_id": self.session_id,
                        "request_id": request_id,
                        "question": f"Tool `{tool_name}` returned ambiguous results. How should we proceed?",
                        "context": json.dumps(result.to_dict()),
                    })
                    decision = "skip"
                    if self.wait_for_decision:
                        try:
                            decision = await asyncio.wait_for(
                                self.wait_for_decision(self.session_id, request_id, result.to_dict()),
                                timeout=300.0,
                            )
                        except asyncio.TimeoutError:
                            decision = "skip"
                    messages.append({"role": "user", "content": f"User decision on ambiguity: {decision}"})

        batch_event = self._maybe_emit_batch_event()
        if batch_event:
            yield batch_event
        if self._dashboard_agent_id:
            state_manager.update_agent_status(self._dashboard_agent_id, "idle")
            await state_manager.broadcast_agent_update(self.session_id, self._dashboard_agent_id)
            await state_manager.broadcast_circuit(self.session_id)
        yield SSEEvent("text", {"chunk": "\n[Agent reached maximum iterations. Task may be incomplete.]"})
        yield SSEEvent("task_complete", {"session_id": self.session_id, "result": "max_iterations_reached", "iterations": self.max_iterations})

    async def _execute_tool_with_retry(
        self,
        request_id: str,
        tool_name: str,
        args: dict,
    ) -> ToolResult:
        """Execute a tool with automatic retry for standard errors."""
        last_result: Optional[ToolResult] = None

        for attempt in range(self.max_retries + 1):
            if self.wait_for_tool_result:
                try:
                    result = await asyncio.wait_for(
                        self.wait_for_tool_result(self.session_id, request_id, {"tool": tool_name, "args": args}),
                        timeout=30.0,
                    )
                except asyncio.TimeoutError:
                    result = ToolResult(tool_name, args, "error", error="Tool execution timed out")
            else:
                result = ToolResult(
                    tool_name, args, "pending",
                    data={"note": "Tool execution delegated to VS Code: extension"},
                )

            last_result = result

            if result.status in ("ok", "success"):
                return result

            retryable = self._is_retryable_error(result)

            if retryable and attempt < self.max_retries:
                if self.autonomy in (AutonomyLevel.OVERRIDE, AutonomyLevel.AUTOPILOT):
                    # In non-DEFAULT modes, auto-retry after backoff
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                else:
                    break
            else:
                break

        return last_result or ToolResult(tool_name, args, "error", error="Unknown execution failure")

    async def _self_resolve(
        self,
        messages: List[Dict[str, str]],
        ambiguous_result: ToolResult,
    ) -> str:
        """AUTOPILOT only: ask the LLM to resolve ambiguity without human input."""
        resolve_messages = list(messages) + [
            {
                "role": "system",
                "content": (
                    "You are in AUTOPILOT mode. A tool returned ambiguous or incomplete results. "
                    "Use your best judgment based on available context to decide the next step. "
                    "Respond with a concise decision and reasoning."
                ),
            },
            {
                "role": "user",
                "content": f"Ambiguous result: {json.dumps(ambiguous_result.to_dict())}. How should we proceed?",
            },
        ]
        llm_model = self.model or await select_model(prefer_local=True, subagent_mode=self.subagent_mode)
        resolution = ""
        async for chunk in chat_completion(resolve_messages, model=llm_model, stream=False):
            resolution += chunk
        return resolution

    def _maybe_emit_batch_event(self) -> Optional[SSEEvent]:
        """If we have a non-empty change batch, return a batch_ready event."""
        if self._change_batch and self._change_batch.changes:
            self._change_batch.status = BatchStatus.REVIEWING
            return SSEEvent("change_batch_ready", {
                "session_id": self.session_id,
                "batch_id": self._change_batch.batch_id,
                "stats": self._change_batch.stats(),
                "changes": [c.summary() for c in self._change_batch.changes],
            })
        return None

    @staticmethod
    def _extract_tool_calls(text: str) -> List[Dict[str, Any]]:
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

    @staticmethod
    def _is_retryable_error(result: ToolResult) -> bool:
        """Heuristic: determine if a tool error is standard/retryable."""
        if result.status in ("ok", "success"):
            return False
        error_str = (result.error or "").lower()
        retryable_keywords = [
            "timeout", "connection", "refused", "econnrefused",
            "temporarily", "rate limit", "503", "502", "504",
            "busy", "unavailable", "network",
        ]
        return any(kw in error_str for kw in retryable_keywords)

    async def run_swarm_path(
        self,
        task: str,
        workspace_context: str = "",
        call_agent_fn=None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Execute the swarm as a SignalPath DAG with autonomy-aware gates.
        Supports tool-enabled subagents and orchestrator model selection.
        """
        yield SSEEvent("text", {"chunk": "🐝 **Swarm Activated**\n\n"})

        # Initialize dashboard swarm tree
        root = state_manager.create_swarm(self.session_id, task)
        root.system_prompt = f"Orchestrator for: {task}"
        state_manager.update_agent_status(root.agent_id, "active")
        await state_manager.broadcast_agent_update(self.session_id, root.agent_id)
        await state_manager.broadcast_circuit(self.session_id)

        # --- Phase 1: Architect + Researcher (parallel) ---
        arch_agent = state_manager.spawn_agent(root.agent_id, "architect", "Architect", "System design and planning specialist.")
        research_agent = state_manager.spawn_agent(root.agent_id, "researcher", "Researcher", "Codebase investigation specialist.")
        await state_manager.broadcast_agent_update(self.session_id, arch_agent.agent_id)
        await state_manager.broadcast_agent_update(self.session_id, research_agent.agent_id)

        if self.autonomy == AutonomyLevel.DEFAULT:
            req_id = f"phase1-{str(uuid.uuid4())[:8]}"
            yield SSEEvent("approval_required", {
                "session_id": self.session_id,
                "request_id": req_id,
                "phase": "phase1",
                "message": "Swarm wants to launch Architect + Researcher. Approve?",
            })
            approved = False
            if self.wait_for_approval:
                try:
                    approved = await asyncio.wait_for(
                        self.wait_for_approval(self.session_id, req_id, {"phase": "phase1", "description": "Launch Architect + Researcher"}),
                        timeout=300.0,
                    )
                except asyncio.TimeoutError:
                    approved = False
            if not approved:
                state_manager.update_agent_status(arch_agent.agent_id, "paused")
                state_manager.update_agent_status(research_agent.agent_id, "paused")
                await state_manager.broadcast_agent_update(self.session_id, arch_agent.agent_id)
                await state_manager.broadcast_agent_update(self.session_id, research_agent.agent_id)
                await state_manager.broadcast_circuit(self.session_id)
                yield SSEEvent("text", {"chunk": "\n[Swarm halted at Phase 1 by user.]"})
                return

        state_manager.update_agent_status(arch_agent.agent_id, "active")
        state_manager.update_agent_status(research_agent.agent_id, "active")
        await state_manager.broadcast_agent_update(self.session_id, arch_agent.agent_id)
        await state_manager.broadcast_agent_update(self.session_id, research_agent.agent_id)
        await state_manager.broadcast_circuit(self.session_id)

        yield SSEEvent("text", {"chunk": "**[Architect]** Analyzing task and creating plan...\n"})
        yield SSEEvent("text", {"chunk": "**[Researcher]** Investigating workspace...\n\n"})

        if call_agent_fn:
            plan, research = await asyncio.gather(
                asyncio.create_task(call_agent_fn("architect", f"Task: {task}\n\nWorkspace context:\n{workspace_context}\n\nExplore the codebase with list_files and read_file, then create a concise 3-bullet implementation plan. Use tools. No essays.", use_tools=True, parent_agent_id=arch_agent.agent_id)),
                asyncio.create_task(call_agent_fn("researcher", f"Task: {task}\n\nWorkspace context:\n{workspace_context}\n\nUse list_files and read_file to explore. List the top 5 files that need changing with 1-line reasons. Use tools. No essays.", use_tools=True, parent_agent_id=research_agent.agent_id)),
            )
        else:
            plan = "(Architect output placeholder)"
            research = "(Researcher output placeholder)"

        state_manager.update_agent_status(arch_agent.agent_id, "committed")
        state_manager.update_agent_status(research_agent.agent_id, "committed")
        await state_manager.broadcast_agent_update(self.session_id, arch_agent.agent_id)
        await state_manager.broadcast_agent_update(self.session_id, research_agent.agent_id)
        await state_manager.broadcast_circuit(self.session_id)

        plan_short = plan[:800] + "..." if len(plan) > 800 else plan
        research_short = research[:800] + "..." if len(research) > 800 else research
        yield SSEEvent("text", {"chunk": "**[Architect]** Plan:\n" + plan_short + "\n\n"})
        yield SSEEvent("text", {"chunk": "**[Researcher]** Findings:\n" + research_short + "\n\n"})
        yield self._emit_token_usage()

        # --- Phase 2: Coder (sequential, with tool access) ---
        coder_agent = state_manager.spawn_agent(root.agent_id, "coder", "Coder", "Code implementation specialist.")
        await state_manager.broadcast_agent_update(self.session_id, coder_agent.agent_id)

        if self.autonomy == AutonomyLevel.DEFAULT:
            req_id = f"phase2-{str(uuid.uuid4())[:8]}"
            yield SSEEvent("approval_required", {
                "session_id": self.session_id,
                "request_id": req_id,
                "phase": "phase2",
                "message": "Swarm wants to launch Coder with plan + research. Approve?",
            })
            approved = False
            if self.wait_for_approval:
                try:
                    approved = await asyncio.wait_for(
                        self.wait_for_approval(self.session_id, req_id, {"phase": "phase2", "description": "Launch Coder"}),
                        timeout=300.0,
                    )
                except asyncio.TimeoutError:
                    approved = False
            if not approved:
                state_manager.update_agent_status(coder_agent.agent_id, "paused")
                await state_manager.broadcast_agent_update(self.session_id, coder_agent.agent_id)
                await state_manager.broadcast_circuit(self.session_id)
                yield SSEEvent("text", {"chunk": "\n[Swarm halted at Phase 2 by user.]"})
                return

        state_manager.update_agent_status(coder_agent.agent_id, "active")
        await state_manager.broadcast_agent_update(self.session_id, coder_agent.agent_id)
        await state_manager.broadcast_circuit(self.session_id)

        yield SSEEvent("text", {"chunk": "**[Coder]** Writing code with tool access...\n\n"})

        if call_agent_fn:
            code = await call_agent_fn(
                "coder",
                f"Task: {task}\n\nPlan:\n{plan[:1500]}\n\nResearch:\n{research[:1500]}\n\nWorkspace context:\n{workspace_context}\n\n"
                "Implement the code. Use read_file, write_file, list_files, run_command. "
                "Output ONLY tool JSON blocks. No explanations. No markdown essays. Just tools.",
                use_tools=True,
                parent_agent_id=coder_agent.agent_id,
            )
        else:
            code = "(Coder output placeholder)"

        state_manager.update_agent_status(coder_agent.agent_id, "committed")
        await state_manager.broadcast_agent_update(self.session_id, coder_agent.agent_id)
        await state_manager.broadcast_circuit(self.session_id)

        code_short = code[:800] + "..." if len(code) > 800 else code
        yield SSEEvent("text", {"chunk": "**[Coder]** " + code_short + "\n\n"})
        yield self._emit_token_usage()

        # --- Phase 3: Tester + Debugger (parallel, with tool access) ---
        tester_agent = state_manager.spawn_agent(root.agent_id, "tester", "Tester", "Test writing and validation specialist.")
        debugger_agent = state_manager.spawn_agent(root.agent_id, "debugger", "Debugger", "Bug finding and fixing specialist.")
        await state_manager.broadcast_agent_update(self.session_id, tester_agent.agent_id)
        await state_manager.broadcast_agent_update(self.session_id, debugger_agent.agent_id)

        if self.autonomy == AutonomyLevel.DEFAULT:
            req_id = f"phase3-{str(uuid.uuid4())[:8]}"
            yield SSEEvent("approval_required", {
                "session_id": self.session_id,
                "request_id": req_id,
                "phase": "phase3",
                "message": "Swarm wants to launch Tester + Debugger. Approve?",
            })
            approved = False
            if self.wait_for_approval:
                try:
                    approved = await asyncio.wait_for(
                        self.wait_for_approval(self.session_id, req_id, {"phase": "phase3", "description": "Launch Tester + Debugger"}),
                        timeout=300.0,
                    )
                except asyncio.TimeoutError:
                    approved = False
            if not approved:
                state_manager.update_agent_status(tester_agent.agent_id, "paused")
                state_manager.update_agent_status(debugger_agent.agent_id, "paused")
                await state_manager.broadcast_agent_update(self.session_id, tester_agent.agent_id)
                await state_manager.broadcast_agent_update(self.session_id, debugger_agent.agent_id)
                await state_manager.broadcast_circuit(self.session_id)
                yield SSEEvent("text", {"chunk": "\n[Swarm halted at Phase 3 by user.]"})
                return

        state_manager.update_agent_status(tester_agent.agent_id, "active")
        state_manager.update_agent_status(debugger_agent.agent_id, "active")
        await state_manager.broadcast_agent_update(self.session_id, tester_agent.agent_id)
        await state_manager.broadcast_agent_update(self.session_id, debugger_agent.agent_id)
        await state_manager.broadcast_circuit(self.session_id)

        yield SSEEvent("text", {"chunk": "**[Tester]** Writing tests and checking edge cases...\n"})
        yield SSEEvent("text", {"chunk": "**[Debugger]** Running final review...\n\n"})

        if call_agent_fn:
            tests, review = await asyncio.gather(
                asyncio.create_task(call_agent_fn(
                    "tester",
                    f"Task: {task}\n\nPlan:\n{plan[:1000]}\n\nCode:\n{code[:1000]}\n\n"
                    "Write tests. Use file tools. Output ONLY tool JSON. No essays.",
                    use_tools=True,
                    parent_agent_id=tester_agent.agent_id,
                )),
                asyncio.create_task(call_agent_fn(
                    "debugger",
                    f"Task: {task}\n\nPlan:\n{plan[:1000]}\n\nCode:\n{code[:1000]}\n\n"
                    "Review for bugs. Use file tools. Output ONLY tool JSON. No essays.",
                    use_tools=True,
                    parent_agent_id=debugger_agent.agent_id,
                )),
            )
        else:
            tests = "(Tester output placeholder)"
            review = "(Debugger output placeholder)"

        state_manager.update_agent_status(tester_agent.agent_id, "committed")
        state_manager.update_agent_status(debugger_agent.agent_id, "committed")
        await state_manager.broadcast_agent_update(self.session_id, tester_agent.agent_id)
        await state_manager.broadcast_agent_update(self.session_id, debugger_agent.agent_id)
        await state_manager.broadcast_circuit(self.session_id)

        tests_short = tests[:600] + "..." if len(tests) > 600 else tests
        review_short = review[:600] + "..." if len(review) > 600 else review
        yield SSEEvent("text", {"chunk": "**[Tester]** " + tests_short + "\n\n"})
        yield SSEEvent("text", {"chunk": "**[Debugger]** " + review_short + "\n\n"})
        yield self._emit_token_usage()

        # --- Phase 4: Execution (with tools) ---
        # If the task involves coding, let an executor agent actually implement the plan using tools.
        executor_agent = state_manager.spawn_agent(root.agent_id, "executor", "Executor", "Swarm execution specialist.")
        await state_manager.broadcast_agent_update(self.session_id, executor_agent.agent_id)
        state_manager.update_agent_status(executor_agent.agent_id, "active")
        await state_manager.broadcast_circuit(self.session_id)

        yield SSEEvent("text", {"chunk": "**[Executor]** Implementing changes with tool access...\n\n"})

        exec_messages = [
            {"role": "system", "content": (
                "You are the Swarm Executor. You have tools: read_file, write_file, list_files, run_command, search_files, web_search. "
                "Implement the plan. USE TOOLS. No essays. No explanations. Just tools and brief results. "
                "When you need a tool, output ONLY a JSON block like:\n"
                '```tool\n{"tool": "write_file", "args": {"path": "...", "content": "..."}}\n```'
            )},
            {"role": "user", "content": (
                f"Task: {task}\n\n"
                f"Plan:\n{plan[:1500]}\n\n"
                f"Research:\n{research[:1500]}\n\n"
                f"Code:\n{code[:1500]}\n\n"
                f"Tests:\n{tests[:800]}\n\n"
                f"Review:\n{review[:800]}\n\n"
                f"Workspace context:\n{workspace_context}\n\n"
                "Implement the changes. Write files. Run commands. Verify."
            )},
        ]

        if call_agent_fn:
            exec_result = await call_agent_fn(
                "executor",
                f"Task: {task}\n\n"
                f"Plan:\n{plan[:1500]}\n\n"
                f"Research:\n{research[:1500]}\n\n"
                f"Code:\n{code[:1500]}\n\n"
                f"Tests:\n{tests[:800]}\n\n"
                f"Review:\n{review[:800]}\n\n"
                f"Workspace context:\n{workspace_context}\n\n"
                "Implement the changes. Write files. Run commands. Verify. "
                "Output ONLY tool JSON blocks. No essays. No explanations.",
                use_tools=True,
                parent_agent_id=executor_agent.agent_id,
            )
            exec_short = exec_result[:800] + "..." if len(exec_result) > 800 else exec_result
            yield SSEEvent("text", {"chunk": "\n**[Executor]** " + exec_short + "\n\n"})
        else:
            async for event in self.run_agent_loop(
                messages=exec_messages,
                system_prompt=exec_messages[0]["content"],
                workspace_context=workspace_context,
                agent_role="executor",
                agent_name="Executor",
                parent_agent_id=executor_agent.agent_id,
            ):
                # Forward execution events, but skip the final task_complete since we'll emit our own
                if event.event_type == "task_complete":
                    yield SSEEvent("text", {"chunk": "\n**[Executor]** Implementation complete.\n\n"})
                    state_manager.update_agent_status(executor_agent.agent_id, "committed")
                    await state_manager.broadcast_agent_update(self.session_id, executor_agent.agent_id)
                    break
                else:
                    yield event

        state_manager.update_agent_status(executor_agent.agent_id, "committed")
        await state_manager.broadcast_agent_update(self.session_id, executor_agent.agent_id)

        state_manager.update_agent_status(root.agent_id, "committed")
        await state_manager.broadcast_agent_update(self.session_id, root.agent_id)
        await state_manager.broadcast_circuit(self.session_id)

        yield self._emit_token_usage()
        yield SSEEvent("task_complete", {
            "session_id": self.session_id,
            "result": "Swarm complete",
            "artifacts": {"plan": plan, "research": research, "code": code, "tests": tests, "review": review},
        })
