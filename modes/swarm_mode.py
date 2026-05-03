"""Swarm Mode — Multiple specialized agents collaborate to solve complex problems."""

import json
import asyncio
from typing import List, Dict, Any, AsyncGenerator
from core.model_router import chat_completion, select_model


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
}


class SwarmOrchestrator:
    """Orchestrates multiple agents working together."""
    
    def __init__(self, max_agents: int = 5):
        self.max_agents = max_agents
        self.messages: List[Dict[str, str]] = []
    
    async def run(
        self,
        task: str,
        workspace_context: str = "",
    ) -> AsyncGenerator[str, None]:
        """Run the swarm on a task."""
        yield "🐝 **Swarm Activated**\n\n"
        
        # Phase 1: Architect analyzes and creates a plan
        yield "**[Architect]** Analyzing task and creating plan...\n\n"
        plan = await self._architect_plan(task, workspace_context)
        yield plan + "\n\n"
        
        # Phase 2: Researcher investigates the codebase
        yield "**[Researcher]** Investigating workspace...\n\n"
        research = await self._researcher_investigate(task, workspace_context, plan)
        yield research + "\n\n"
        
        # Phase 3: Coder implements the solution
        yield "**[Coder]** Writing code...\n\n"
        code = await self._coder_implement(task, workspace_context, plan, research)
        yield code + "\n\n"
        
        # Phase 4: Tester validates
        yield "**[Tester]** Writing tests and checking edge cases...\n\n"
        tests = await self._tester_validate(task, workspace_context, plan, code)
        yield tests + "\n\n"
        
        # Phase 5: Debugger final review
        yield "**[Debugger]** Final review...\n\n"
        review = await self._debugger_review(task, workspace_context, plan, code, tests)
        yield review + "\n\n"
        
        yield "✅ **Swarm complete.** Review the output above and approve changes to apply them.\n"
    
    async def _architect_plan(self, task: str, workspace_context: str) -> str:
        messages = [
            {"role": "system", "content": AGENT_ROLES["architect"]["system"]},
            {"role": "user", "content": f"Task: {task}\n\nWorkspace context:\n{workspace_context}\n\nCreate a concise implementation plan."},
        ]
        model = await select_model(prefer_local=True)
        result = ""
        async for chunk in chat_completion(messages, model=model, stream=False):
            result += chunk
        return result
    
    async def _researcher_investigate(self, task: str, workspace_context: str, plan: str) -> str:
        messages = [
            {"role": "system", "content": AGENT_ROLES["researcher"]["system"]},
            {"role": "user", "content": f"Task: {task}\n\nPlan:\n{plan}\n\nWorkspace context:\n{workspace_context}\n\nWhat files need to be read or modified? List them with reasoning."},
        ]
        model = await select_model(prefer_local=True)
        result = ""
        async for chunk in chat_completion(messages, model=model, stream=False):
            result += chunk
        return result
    
    async def _coder_implement(self, task: str, workspace_context: str, plan: str, research: str) -> str:
        messages = [
            {"role": "system", "content": AGENT_ROLES["coder"]["system"]},
            {"role": "user", "content": f"Task: {task}\n\nPlan:\n{plan}\n\nResearch:\n{research}\n\nWorkspace context:\n{workspace_context}\n\nWrite the code implementation. Provide full file contents for any new or modified files."},
        ]
        model = await select_model(prefer_local=True)
        result = ""
        async for chunk in chat_completion(messages, model=model, stream=False):
            result += chunk
        return result
    
    async def _tester_validate(self, task: str, workspace_context: str, plan: str, code: str) -> str:
        messages = [
            {"role": "system", "content": AGENT_ROLES["tester"]["system"]},
            {"role": "user", "content": f"Task: {task}\n\nPlan:\n{plan}\n\nCode:\n{code}\n\nWrite tests and identify any edge cases or issues."},
        ]
        model = await select_model(prefer_local=True)
        result = ""
        async for chunk in chat_completion(messages, model=model, stream=False):
            result += chunk
        return result
    
    async def _debugger_review(self, task: str, workspace_context: str, plan: str, code: str, tests: str) -> str:
        messages = [
            {"role": "system", "content": AGENT_ROLES["debugger"]["system"]},
            {"role": "user", "content": f"Task: {task}\n\nPlan:\n{plan}\n\nCode:\n{code}\n\nTests:\n{tests}\n\nDo a final review. Any bugs, issues, or improvements?"},
        ]
        model = await select_model(prefer_local=True)
        result = ""
        async for chunk in chat_completion(messages, model=model, stream=False):
            result += chunk
        return result


async def swarm_run(
    task: str,
    workspace_context: str = "",
) -> AsyncGenerator[str, None]:
    """Run the full agent swarm on a task."""
    orchestrator = SwarmOrchestrator()
    async for chunk in orchestrator.run(task, workspace_context):
        yield chunk
