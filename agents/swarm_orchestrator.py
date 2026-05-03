"""
Swarm Orchestrator — delegates tasks to specialized agents and coordinates their output.
"""
import asyncio
from typing import List, Dict, AsyncGenerator
from .base import AGENT_REGISTRY
from core.model_router import router

class SwarmOrchestrator:
    def __init__(self):
        self.agents = AGENT_REGISTRY

    async def run_single(self, agent_key: str, task: str, context: str = "") -> str:
        agent = self.agents.get(agent_key)
        if not agent:
            return f"[Error] Unknown agent: {agent_key}"

        messages = [
            {"role": "system", "content": agent.prompt_template},
            {"role": "user", "content": f"Task: {task}\n\nContext: {context}"}
        ]
        return await router.chat(messages, mode="agent")

    async def run_swarm(self, task: str, context: str = "") -> AsyncGenerator[Dict, None]:
        """
        Run multiple agents in parallel, yield results as they complete.
        """
        # Determine which agents to invoke based on task keywords
        selected = self._select_agents(task)
        
        yield {"agent": "orchestrator", "status": "started", "selected_agents": list(selected.keys())}

        # Run agents concurrently
        async def run_agent(key, agent):
            try:
                result = await self.run_single(key, task, context)
                return {"agent": agent.name, "result": result, "status": "done"}
            except Exception as e:
                return {"agent": agent.name, "error": str(e), "status": "error"}

        tasks = [run_agent(k, a) for k, a in selected.items()]
        for coro in asyncio.as_completed(tasks):
            result = await coro
            yield result

        # Final synthesis
        yield {"agent": "orchestrator", "status": "synthesizing"}
        synthesis = await self._synthesize(task, context)
        yield {"agent": "Synthesis", "result": synthesis, "status": "done"}

    def _select_agents(self, task: str) -> Dict:
        task_lower = task.lower()
        selected = {}

        if any(k in task_lower for k in ("code", "function", "class", "implement", "refactor", "debug")):
            selected["code"] = self.agents["code"]
        if any(k in task_lower for k in ("review", "check", "audit", "security", "bug")):
            selected["review"] = self.agents["review"]
        if any(k in task_lower for k in ("test", "spec", "coverage", "unit test")):
            selected["test"] = self.agents["test"]
        if any(k in task_lower for k in ("doc", "readme", "documentation", "explain")):
            selected["doc"] = self.agents["doc"]
        if any(k in task_lower for k in ("plan", "architecture", "design", "break down")):
            selected["plan"] = self.agents["plan"]

        # Default to code + review if nothing matched
        if not selected:
            selected = {"code": self.agents["code"], "review": self.agents["review"]}

        return selected

    async def _synthesize(self, task: str, context: str) -> str:
        messages = [
            {"role": "system", "content": "You are the swarm orchestrator. Synthesize the outputs from multiple specialized agents into a coherent, actionable response."},
            {"role": "user", "content": f"Original task: {task}\n\nContext: {context}\n\nProvide a final synthesis."}
        ]
        return await router.chat(messages, mode="swarm")

orchestrator = SwarmOrchestrator()
