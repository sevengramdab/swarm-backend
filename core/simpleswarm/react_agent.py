"""
react_agent.py
==============
ReAct-pattern agent with multi-turn tool use.

ELI5: The agent thinks out loud (Reasoning), then Acts (calls a tool),
      observes the result, and thinks again. It can chain multiple
      tool calls in a row before producing a final answer.

This is the "everything Kimi Code can do" engine:
- File read/write/edit
- Shell execution
- Web search
- Directory listing
- Grep search
- Self-correction on errors
"""
from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .web_search import WebSearchTool


REACT_SYSTEM_PROMPT = """You are SwarmCoder-ReAct, an autonomous coding agent with tool use.

AVAILABLE TOOLS:
- read_file(path, offset=1, n_lines=100): Read part of a file
- write_file(path, content): Create or overwrite a file with FULL content
- edit_file(path, old, new): Replace exact text in a file
- list_dir(path="."): List files in a directory
- grep(pattern, path=".", glob="*.py"): Search files with regex
- shell(command, timeout=60): Run a shell command
- web_search(query, max_results=5): Search the web for information
- done(summary): Mark task as complete

TOOL USE FORMAT:
To use a tool, respond with ONLY this JSON:
{"tool": "tool_name", "params": {"key": "value"}, "reasoning": "why you're using this tool"}

CRITICAL RULES:
1. Use RELATIVE paths from project root
2. For edit_file, old text must match EXACTLY
3. write_file requires the COMPLETE file content
4. If a tool returns an error, try a different approach
5. You can chain multiple tool calls — the result of each will be shown to you
6. After 25 turns, if core work is done, use done() to finish
7. Think step by step. It's OK to use 5-10 tool calls to complete a task."""


def _extract_json(raw: str) -> Optional[dict]:
    """Extract JSON from LLM response."""
    for marker in ["```json", "```"]:
        if marker in raw:
            parts = raw.split(marker)
            if len(parts) >= 2:
                candidate = parts[1].split("```")[0].strip()
                try:
                    return json.loads(candidate, strict=False)
                except Exception:
                    pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start:end+1], strict=False)
        except Exception:
            pass
    return None


@dataclass
class Turn:
    turn_number: int
    reasoning: str
    tool: str
    params: dict
    result: dict
    success: bool
    timestamp: float = field(default_factory=time.time)


@dataclass
class ReActTask:
    task_id: str
    goal: str
    turns: List[Turn] = field(default_factory=list)
    status: str = "running"  # running / completed / failed
    result_summary: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class ReActAgent:
    """Multi-turn tool-use agent."""

    def __init__(self, llm, fs, shell, project_dir: str = "."):
        self.llm = llm
        self.fs = fs
        self.shell = shell
        self.web_search = WebSearchTool()
        self.project_dir = project_dir

    def run(self, task: ReActTask, stop_event, max_turns: int = 25) -> None:
        """Execute the ReAct loop until done, max turns, or stopped."""
        try:
            for turn_num in range(1, max_turns + 1):
                if stop_event.is_set():
                    task.status = "failed"
                    task.result_summary = "Stopped by user."
                    return

                # Build conversation history
                history = self._build_history(task)
                result = self.llm.chat(REACT_SYSTEM_PROMPT, history, temperature=0.2, timeout=120)

                if not result.get("success"):
                    time.sleep(2)
                    continue

                response = result["response"]
                data = _extract_json(response)

                if data is None:
                    # LLM didn't return valid JSON — ask again with stronger hint
                    task.turns.append(Turn(
                        turn_number=turn_num,
                        reasoning="LLM response parsing failed",
                        tool="none",
                        params={},
                        result={"error": "Could not parse LLM response as JSON", "raw": response[:200]},
                        success=False,
                    ))
                    continue

                tool = data.get("tool", "")
                params = data.get("params", {})
                reasoning = data.get("reasoning", "")

                # Execute the tool
                tool_result = self._execute_tool(tool, params)

                task.turns.append(Turn(
                    turn_number=turn_num,
                    reasoning=reasoning,
                    tool=tool,
                    params=params,
                    result=tool_result,
                    success=tool_result.get("success", False),
                ))
                task.updated_at = time.time()

                if tool == "done":
                    task.status = "completed"
                    task.result_summary = tool_result.get("summary", "Task completed.")
                    return

            # Max turns reached
            task.status = "completed"
            task.result_summary = f"Reached max turns ({max_turns}). Partial work may be done."

        except Exception as e:
            task.status = "failed"
            task.result_summary = f"Exception: {str(e)}"
            traceback.print_exc()

    def _build_history(self, task: ReActTask) -> str:
        """Build the full conversation context for the LLM."""
        lines = [f"Goal: {task.goal}", ""]

        if task.turns:
            lines.append("Previous actions and observations:")
            for turn in task.turns[-8:]:  # Keep last 8 turns in context
                result_str = json.dumps(turn.result)[:300].replace("\n", " ")
                status = "OK" if turn.success else "FAILED"
                lines.append(f"  Turn {turn.turn_number}: {turn.tool} -> {status}")
                lines.append(f"    Reasoning: {turn.reasoning[:100]}")
                lines.append(f"    Result: {result_str}")
            lines.append("")

        lines.append("What tool should you use NEXT? Return ONLY JSON.")
        return "\n".join(lines)

    def _execute_tool(self, tool: str, params: dict) -> dict:
        """Execute a single tool call."""
        try:
            if tool == "read_file":
                return self.fs.read_file(
                    params.get("path", ""),
                    params.get("offset", 1),
                    params.get("n_lines", 100),
                )
            elif tool == "write_file":
                path = params.get("path", "")
                content = params.get("content", "")
                if not content.strip():
                    return {"success": False, "error": "Empty content"}
                result = self.fs.write_file(path, content)
                if path.endswith(".py") and result.get("success"):
                    check = self.shell.run(f'python -m py_compile "{path}"', timeout=10)
                    if not check["success"]:
                        result["syntax_warning"] = check.get("stderr", "Syntax error")
                return result
            elif tool == "edit_file":
                path = params.get("path", "")
                result = self.fs.edit_file(
                    path,
                    params.get("old", ""),
                    params.get("new", ""),
                    params.get("replace_all", False),
                )
                if path.endswith(".py") and result.get("success"):
                    check = self.shell.run(f'python -m py_compile "{path}"', timeout=10)
                    if not check["success"]:
                        result["syntax_warning"] = check.get("stderr", "Syntax error")
                return result
            elif tool == "list_dir":
                return self.fs.list_directory(params.get("path", "."))
            elif tool == "grep":
                return self.fs.grep_search(
                    params.get("pattern", "."),
                    params.get("path", "."),
                    params.get("glob", "*.py"),
                )
            elif tool == "shell":
                return self.shell.run(
                    params.get("command", ""),
                    params.get("cwd"),
                    params.get("timeout", 60),
                )
            elif tool == "web_search":
                return self.web_search.search(
                    params.get("query", ""),
                    params.get("max_results", 5),
                )
            elif tool == "done":
                return {"success": True, "summary": params.get("summary", "Task completed.")}
            else:
                return {"success": False, "error": f"Unknown tool: {tool}"}
        except Exception as e:
            return {"success": False, "error": f"Tool execution error: {e}"}

    def to_dict(self, task: ReActTask) -> dict:
        return {
            "task_id": task.task_id,
            "goal": task.goal,
            "status": task.status,
            "result_summary": task.result_summary,
            "turn_count": len(task.turns),
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "turns": [
                {
                    "turn_number": t.turn_number,
                    "tool": t.tool,
                    "params": t.params,
                    "reasoning": t.reasoning,
                    "result": t.result,
                    "success": t.success,
                }
                for t in task.turns
            ],
        }
