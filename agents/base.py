"""
Base Agent class for swarm operations.
"""
from typing import List, Dict

class Agent:
    def __init__(self, name: str, role: str, prompt_template: str):
        self.name = name
        self.role = role
        self.prompt_template = prompt_template

    async def run(self, task: str, context: str = "", history: List[Dict] = None) -> str:
        """Override in subclasses."""
        return f"[{self.name}] Task received: {task}"

class CodeAgent(Agent):
    def __init__(self):
        super().__init__(
            name="Code",
            role="Generate, refactor, and debug code",
            prompt_template="""You are a senior software engineer. Given the task below, produce high-quality, production-ready code.

Task: {task}
Context: {context}

Respond with code and concise explanations."""
        )

class ReviewAgent(Agent):
    def __init__(self):
        super().__init__(
            name="Review",
            role="Review code for bugs, security, and style",
            prompt_template="""You are a meticulous code reviewer. Review the following code/output for issues.

Task: {task}
Code/Output: {context}

List any bugs, security issues, or improvements."""
        )

class TestAgent(Agent):
    def __init__(self):
        super().__init__(
            name="Test",
            role="Write tests and check coverage",
            prompt_template="""You are a QA engineer. Write comprehensive tests for the following code.

Task: {task}
Code: {context}

Provide unit tests with edge cases."""
        )

class DocAgent(Agent):
    def __init__(self):
        super().__init__(
            name="Doc",
            role="Write documentation and READMEs",
            prompt_template="""You are a technical writer. Write clear documentation for the following.

Task: {task}
Context: {context}

Respond with markdown documentation."""
        )

class PlanAgent(Agent):
    def __init__(self):
        super().__init__(
            name="Plan",
            role="Architect and plan features",
            prompt_template="""You are a software architect. Create a detailed implementation plan.

Task: {task}
Context: {context}

Break down into steps, files, and dependencies."""
        )

AGENT_REGISTRY = {
    "code": CodeAgent(),
    "review": ReviewAgent(),
    "test": TestAgent(),
    "doc": DocAgent(),
    "plan": PlanAgent(),
}
