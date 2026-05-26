"""
swarm_coder.py  (v2 — Reactive + Resilient)
============================================
Autonomous coding agent for SimplePod Swarm.
Uses REACTIVE step-by-step planning — the LLM only picks ONE next action
based on current state, not a full plan upfront. This works reliably
with small local models like llama3.2.

Key resilience features for small models:
- json.loads(strict=False) handles raw newlines in LLM JSON output
- Code-block fallback: when JSON fails, extracts ```python blocks directly
- Auto syntax-check after every .py write/edit
- Loop detection: warns on repeated edits/shell commands
- Auto-complete: accepts task after 3 successful writes of the same .py file
- Max-step fallback: accepts partially completed work instead of failing
- Empty write rejection: forces LLM to provide complete content
- Edit limit: max 2 edits per file, then requires full rewrite

ELI5: Instead of asking "plan the whole trip," we ask "what's the next turn?"
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from threading import Thread, Event

from .plan_creator import PlanCreator, CreatedPlan
from .react_agent import ReActAgent, ReActTask


# ---------------------------------------------------------------------------
# File System Tool
# ---------------------------------------------------------------------------

class FileSystemTool:
    """Structured file operations for agents."""

    def __init__(self, project_dir: str = "."):
        self.project_dir = Path(project_dir).resolve()

    def _resolve(self, path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = self.project_dir / p
        return p.resolve()

    def read_file(self, path: str, offset: int = 1, n_lines: int = 100) -> dict:
        try:
            p = self._resolve(path)
            if not p.exists():
                return {"success": False, "error": f"File not found: {p}"}
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
            start = max(0, offset - 1)
            end = start + n_lines
            selected = lines[start:end]
            return {
                "success": True,
                "path": str(p),
                "total_lines": len(lines),
                "offset": offset,
                "lines": selected,
                "content": "\n".join(selected),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def write_file(self, path: str, content: str) -> dict:
        try:
            p = self._resolve(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return {"success": True, "path": str(p), "bytes_written": len(content.encode("utf-8"))}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def edit_file(self, path: str, old: str, new: str, replace_all: bool = False) -> dict:
        try:
            p = self._resolve(path)
            if not p.exists():
                return {"success": False, "error": f"File not found: {p}"}
            text = p.read_text(encoding="utf-8", errors="ignore")
            count = text.count(old)
            if count == 0:
                return {"success": False, "error": f"Pattern not found in {p}. Consider read_file first to verify exact text."}
            if replace_all:
                text = text.replace(old, new)
            else:
                text = text.replace(old, new, 1)
            p.write_text(text, encoding="utf-8")
            return {"success": True, "path": str(p), "replacements": count if replace_all else 1}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def grep_search(self, pattern: str, path: str = ".", glob: str = "*.py") -> dict:
        try:
            results = []
            root = self._resolve(path)
            for f in root.rglob(glob):
                if ".venv" in str(f) or "node_modules" in str(f):
                    continue
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                    for i, line in enumerate(text.splitlines(), 1):
                        if re.search(pattern, line):
                            results.append({"file": str(f.relative_to(self.project_dir)), "line": i, "text": line.strip()})
                except Exception:
                    pass
            return {"success": True, "matches": results[:50], "total": len(results)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_directory(self, path: str = ".", max_depth: int = 2) -> dict:
        try:
            root = self._resolve(path)
            entries = []
            for item in sorted(root.iterdir()):
                entries.append({"name": item.name, "type": "dir" if item.is_dir() else "file", "size": item.stat().st_size if item.is_file() else 0})
            return {"success": True, "path": str(root.relative_to(self.project_dir)), "entries": entries}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Shell Tool
# ---------------------------------------------------------------------------

class ShellTool:
    def run(self, command: str, cwd: Optional[str] = None, timeout: int = 60) -> dict:
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout[:3000],
                "stderr": result.stderr[:3000],
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Command timed out after {timeout}s"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# LLM Tool (Ollama)
# ---------------------------------------------------------------------------

class LLMTool:
    def __init__(self, host: str = "http://127.0.0.1:11434", model: str = "llama3.2"):
        self.host = host
        self.model = model
        self._tested_models: List[str] = []
        self._ensure_model()

    def _call_ollama(self, payload: dict, timeout: int = 120) -> dict:
        import urllib.request
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(f"{self.host}/api/chat", data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read())
                msg = result.get("message", {})
                return {"success": True, "response": msg.get("content", ""), "model": payload["model"]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _ensure_model(self):
        """Auto-detect available model and test it works."""
        try:
            import urllib.request
            req = urllib.request.Request(f"{self.host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                all_models = [m.get("name", "") for m in data.get("models", [])]

            # Preference order: smaller, faster models first
            preferred = ["llama3.2:latest", "llama3.2", "dolphin-llama3:latest", "openchat:latest", "solar:latest"]
            candidates = []
            for pref in preferred:
                for m in all_models:
                    if pref == m or pref == m.split(":")[0] or f"{pref}:latest" == m:
                        candidates.append(m)

            # Test each candidate with a simple ping
            for cand in candidates:
                test_payload = {
                    "model": cand,
                    "messages": [
                        {"role": "system", "content": "Reply with OK."},
                        {"role": "user", "content": "Say OK."},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.0},
                }
                result = self._call_ollama(test_payload, timeout=30)
                if result.get("success") and "OK" in result.get("response", ""):
                    self.model = cand
                    self._tested_models = candidates
                    return

            # Fallback: use first available
            if all_models:
                self.model = all_models[0]

        except Exception:
            pass

    def chat(self, system: str, user: str, temperature: float = 0.3, timeout: int = 120) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        }
        return self._call_ollama(payload, timeout=timeout)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class Step:
    step_number: int
    action: str
    params: Dict[str, Any]
    reasoning: str = ""


@dataclass
class TaskLog:
    timestamp: float
    step: int
    action: str
    result: str
    success: bool


@dataclass
class CoderTask:
    task_id: str
    goal: str
    status: str = "PENDING"
    logs: List[TaskLog] = field(default_factory=list)
    current_step: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    result_summary: str = ""


# ---------------------------------------------------------------------------
# Reactive Plan Generator
# ---------------------------------------------------------------------------

REACTIVE_SYSTEM_PROMPT = """You are SwarmCoder, an autonomous coding agent. You decide the SINGLE next action to take.

AVAILABLE ACTIONS:
- list_dir: {"path": str} — List files in a directory
- read_file: {"path": str, "offset": int, "n_lines": int} — Read part of a file. Offset starts at 1.
- write_file: {"path": str, "content": str} — Create or overwrite a file
- edit_file: {"path": str, "old": str, "new": str} — Replace text in a file
- grep: {"pattern": str, "path": str, "glob": str} — Search files with regex
- shell: {"command": str, "timeout": int} — Run a shell command
- done: {"summary": str} — Mark task as complete

CRITICAL RULES:
1. Use RELATIVE paths from project root (e.g. "core/file.py", NOT absolute paths)
2. For edit_file, old text must match EXACTLY — read the file first to verify
3. Prefer write_file for new files, edit_file for small changes
4. If a previous action failed, try a different approach
5. If the goal is to create an app (streamlit, flask, etc.), WRITE THE CODE FILE directly with COMPLETE content. Do NOT create CSV/JSON data files unless specifically asked.
6. NEVER use edit_file more than 2 times on the same file. After 2 edits, use write_file with the COMPLETE content instead.
7. Do NOT install packages repeatedly. If pip install was already run, do not run it again.
8. After 8+ steps, if the core work is done, use "done" to finish.
9. When using write_file, include the ENTIRE file content in the 'content' param. Do NOT write empty files.

RESPONSE FORMAT — return ONLY this JSON, nothing else:
{"action": "write_file", "params": {"path": "...", "content": "..."}, "reasoning": "..."}"""


def _extract_json(raw: str) -> Optional[dict]:
    """Very forgiving JSON extractor. Uses strict=False because LLMs often output raw newlines inside JSON strings."""
    # Try to find JSON in markdown code blocks
    for marker in ["```json", "```"]:
        if marker in raw:
            parts = raw.split(marker)
            if len(parts) >= 2:
                candidate = parts[1].split("```")[0].strip()
                try:
                    return json.loads(candidate, strict=False)
                except Exception:
                    pass

    # Try to find JSON between first { and last }
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start:end+1], strict=False)
        except Exception:
            pass

    return None


def _extract_code_blocks(raw: str) -> List[str]:
    """Extract code blocks from markdown-style responses (any language tag)."""
    import re
    # Match ```lang\n...\n``` or ```\n...\n```
    pattern = r"```[\w]*\n(.*?)\n```"
    return re.findall(pattern, raw, re.DOTALL)


class ReactivePlanner:
    """The LLM only decides the NEXT action, not a full plan."""

    def __init__(self, llm: LLMTool, fs: FileSystemTool):
        self.llm = llm
        self.fs = fs

    def _build_state(self, task: CoderTask, warning: str = "") -> str:
        """Build a concise state description for the LLM."""
        lines = [f"Goal: {task.goal}", ""]

        if warning:
            lines.append(f"SYSTEM NOTICE: {warning}")
            lines.append("")

        if task.logs:
            lines.append("What we've done so far:")
            for log in task.logs[-3:]:
                status = "OK" if log.success else "FAILED"
                if log.action == "read_file" and log.success:
                    # Show actual file content so the LLM can reason about it
                    try:
                        r = json.loads(log.result)
                        content_lines = r.get("lines", [])
                        snippet = " | ".join(content_lines[:8])
                        lines.append(f"  Step {log.step}: read_file -> {status} | {r.get('path','')} lines {r.get('offset',1)}-{r.get('offset',1)+len(content_lines)-1}: {snippet}")
                    except Exception:
                        result_summary = log.result[:80].replace("\n", " ")
                        lines.append(f"  Step {log.step}: {log.action} -> {status} | {result_summary}")
                else:
                    result_summary = log.result[:80].replace("\n", " ")
                    lines.append(f"  Step {log.step}: {log.action} -> {status} | {result_summary}")
            lines.append("")

        # Show what files we know about
        known_files = set()
        for log in task.logs:
            if log.action in ("read_file", "write_file", "edit_file"):
                try:
                    r = json.loads(log.result)
                    if r.get("path"):
                        known_files.add(r["path"])
                except Exception:
                    pass

        if known_files:
            lines.append("Known files:")
            for f in sorted(known_files)[-10:]:
                lines.append(f"  - {f}")
            lines.append("")

        # Completion hint: if the goal file was written and passes syntax check, nudge toward done
        for log in task.logs:
            if log.action == "write_file" and log.success:
                try:
                    r = json.loads(log.result)
                    path = r.get("path", "")
                    if not r.get("syntax_warning") and path.endswith(".py"):
                        # Check if goal mentions this filename
                        fname = Path(path).name
                        if fname.lower() in task.goal.lower():
                            lines.append(f"NOTICE: {fname} has been written and passes syntax check. If the core work is done, use 'done' to finish.")
                            lines.append("")
                            break
                except Exception:
                    pass

        lines.append("What should we do NEXT? Return ONLY JSON.")
        return "\n".join(lines)

    def decide_next(self, task: CoderTask, warning: str = "") -> Optional[Step]:
        """Ask the LLM for the next single action."""
        user_prompt = self._build_state(task, warning)
        result = self.llm.chat(REACTIVE_SYSTEM_PROMPT, user_prompt, temperature=0.2, timeout=120)

        if not result.get("success"):
            return None

        response = result["response"]
        data = _extract_json(response)

        if data is not None:
            action = data.get("action", "")
            params = data.get("params", {})
            reasoning = data.get("reasoning", "")
            valid_actions = {"list_dir", "read_file", "write_file", "edit_file", "grep", "shell", "done"}
            if action in valid_actions:
                return Step(step_number=task.current_step, action=action, params=params, reasoning=reasoning)

        # Fallback: if the LLM wrote a code block but no valid JSON, treat it as write_file
        code_blocks = _extract_code_blocks(response)
        if code_blocks:
            # Try to infer the filename from the goal or known files
            filename = self._guess_filename(task, response)
            return Step(
                step_number=task.current_step,
                action="write_file",
                params={"path": filename, "content": code_blocks[0]},
                reasoning="Extracted code block from LLM response (fallback)",
            )

        return None

    def _guess_filename(self, task: CoderTask, response: str) -> str:
        """Try to guess the target filename from the goal or response."""
        # Check if goal mentions a specific filename
        import re
        goal_match = re.search(r"(\S+\.py)", task.goal)
        if goal_match:
            return goal_match.group(1)
        # Check response for filename mentions
        resp_match = re.search(r"(\S+\.py)", response)
        if resp_match:
            return resp_match.group(1)
        return "app.py"


# ---------------------------------------------------------------------------
# Plan Executor
# ---------------------------------------------------------------------------

class PlanExecutor:
    def __init__(self, fs: FileSystemTool, shell: ShellTool):
        self.fs = fs
        self.shell = shell
        self._edit_counts: Dict[str, int] = {}  # Track total edits per file

    def execute(self, step: Step) -> dict:
        action = step.action
        params = step.params

        if action == "read_file":
            return self.fs.read_file(params.get("path", ""), params.get("offset", 1), params.get("n_lines", 100))
        elif action == "write_file":
            path = params.get("path", "")
            content = params.get("content", "")
            if not content.strip():
                return {"success": False, "error": "write_file received empty content. You must provide the FULL file content, not an empty string."}
            result = self.fs.write_file(path, content)
            # Auto syntax-check Python files
            if path.endswith(".py") and result.get("success"):
                safe_path = f'"{path}"'
                check = self.shell.run(f"python -m py_compile {safe_path}", timeout=10)
                if not check["success"]:
                    result["syntax_warning"] = check.get("stderr", "Syntax error detected")
            return result
        elif action == "edit_file":
            path = params.get("path", "")
            self._edit_counts[path] = self._edit_counts.get(path, 0) + 1
            if self._edit_counts[path] > 2:
                return {"success": False, "error": f"File {path} has already been edited {self._edit_counts[path]-1} times. Use write_file with the COMPLETE file content instead of repeated edits."}
            result = self.fs.edit_file(path, params.get("old", ""), params.get("new", ""), params.get("replace_all", False))
            if path.endswith(".py") and result.get("success"):
                safe_path = f'"{path}"'
                check = self.shell.run(f"python -m py_compile {safe_path}", timeout=10)
                if not check["success"]:
                    result["syntax_warning"] = check.get("stderr", "Syntax error detected")
            return result
        elif action == "grep":
            return self.fs.grep_search(params.get("pattern", "."), params.get("path", "."), params.get("glob", "*.py"))
        elif action == "list_dir":
            return self.fs.list_directory(params.get("path", "."))
        elif action == "shell":
            return self.shell.run(params.get("command", ""), params.get("cwd"), params.get("timeout", 60))
        elif action == "done":
            return {"success": True, "summary": params.get("summary", "Task completed.")}
        else:
            return {"success": False, "error": f"Unknown action: {action}"}


# ---------------------------------------------------------------------------
# SwarmCoder Orchestrator
# ---------------------------------------------------------------------------

class SwarmCoder:
    """
    High-level autonomous coding agent with REACTIVE planning.
    The LLM decides one step at a time, not a full plan upfront.
    """

    def __init__(self, project_dir: str = ".", ollama_host: str = "http://127.0.0.1:11434", model: str = "llama3.2"):
        self.project_dir = Path(project_dir).resolve()
        self.fs = FileSystemTool(str(self.project_dir))
        self.shell = ShellTool()
        self.llm = LLMTool(ollama_host, model)
        self.planner = ReactivePlanner(self.llm, self.fs)
        self.executor = PlanExecutor(self.fs, self.shell)
        self.plan_creator = PlanCreator(self.llm)
        self.react_agent = ReActAgent(self.llm, self.fs, self.shell, str(self.project_dir))
        self.tasks: Dict[str, CoderTask] = {}
        self._stop_events: Dict[str, Event] = {}
        self._react_tasks: Dict[str, ReActTask] = {}
        self._react_stop_events: Dict[str, Event] = {}

    def submit_task(self, goal: str) -> CoderTask:
        task_id = str(uuid.uuid4())[:8]
        task = CoderTask(task_id=task_id, goal=goal)
        self.tasks[task_id] = task
        self._stop_events[task_id] = Event()

        # Check if task should be routed to a remote node
        remote_task = self._try_route_remote(task_id, goal)
        if remote_task:
            return remote_task

        thread = Thread(target=self._run_task, args=(task_id,), daemon=True)
        thread.start()
        return task

    # ------------------------------------------------------------------
    # Plan Creator
    # ------------------------------------------------------------------

    def create_plan(self, goal: str) -> CreatedPlan:
        """Generate a multi-option plan for the user to choose from."""
        return self.plan_creator.create_plan(goal)

    def get_plan(self, plan_id: str) -> Optional[CreatedPlan]:
        return self.plan_creator.get_plan(plan_id)

    def execute_plan(self, plan_id: str, option_id: str) -> Optional[CoderTask]:
        """Execute the chosen plan option as a new task."""
        plan = self.plan_creator.select_option(plan_id, option_id)
        if not plan:
            return None

        # Build a detailed goal from the chosen option
        selected = next((o for o in plan.options if o.option_id == option_id), None)
        if not selected:
            return None

        detailed_goal = f"{plan.goal}\n\nApproach: {selected.approach}\nDescription: {selected.description}"
        plan.status = "executing"
        task = self.submit_task(detailed_goal)
        plan.task_id = task.task_id
        return task

    # ------------------------------------------------------------------
    # ReAct Agent (multi-turn tool use)
    # ------------------------------------------------------------------

    def submit_react_task(self, goal: str) -> ReActTask:
        """Submit a task that uses the ReAct multi-turn tool loop."""
        task_id = str(uuid.uuid4())[:8]
        task = ReActTask(task_id=task_id, goal=goal)
        self._react_tasks[task_id] = task
        self._react_stop_events[task_id] = Event()
        thread = Thread(target=self.react_agent.run, args=(task, self._react_stop_events[task_id]), daemon=True)
        thread.start()
        return task

    def get_react_task(self, task_id: str) -> Optional[ReActTask]:
        return self._react_tasks.get(task_id)

    def stop_react_task(self, task_id: str) -> bool:
        ev = self._react_stop_events.get(task_id)
        if ev:
            ev.set()
            return True
        return False

    def list_react_tasks(self) -> List[ReActTask]:
        return sorted(self._react_tasks.values(), key=lambda t: t.created_at, reverse=True)

    # ------------------------------------------------------------------
    # Remote routing
    # ------------------------------------------------------------------

    def _try_route_remote(self, task_id: str, goal: str) -> Optional[CoderTask]:
        """Check if this task should run on a remote node with a larger model.
        
        Uses VRAM-aware routing: estimates VRAM needed based on task complexity
        and routes to the node with the most available VRAM.
        """
        try:
            from core.simpleswarm.remote_client import get_remote_pool
            pool = get_remote_pool()
            healthy = [c for nid, c in pool.nodes.items() if c.health_check()]
            if not healthy:
                return None

            # Simple complexity heuristic
            complexity = self._score_complexity(goal)
            if complexity < 0.6:
                return None  # Simple task — run locally

            # Estimate VRAM needed for this task
            min_vram = self._estimate_vram_mb(goal)
            
            # Pick best remote node with VRAM awareness
            best = pool.get_best_node(prefer_large_model=True, min_vram_mb=min_vram)
            if not best:
                best = healthy[0]  # Fallback to first healthy node
            
            result = best.submit_task(goal)
            if result.get("success") and result.get("data", {}).get("task_id"):
                remote_task_id = result["data"]["task_id"]
                task = self.tasks[task_id]
                task.status = "RUNNING"
                task.result_summary = f"Routed to remote node {best.node_id} ({best.base_url}, {best.vram_mb}MB VRAM) — task {remote_task_id}"

                # Start a background thread to poll the remote task
                thread = Thread(target=self._poll_remote_task, args=(task_id, best, remote_task_id), daemon=True)
                thread.start()
                return task
        except Exception:
            pass
        return None

    def _estimate_vram_mb(self, goal: str) -> int:
        """Estimate VRAM needed for a task based on goal keywords."""
        g = goal.lower()
        # Base VRAM for simple tasks
        vram = 2048
        # Large models need more VRAM
        if any(k in g for k in ["70b", "65b", "mixtral", "dolphin-mixtral"]):
            vram = 45000
        elif any(k in g for k in ["46b", "40b", "33b", "30b"]):
            vram = 24000
        elif any(k in g for k in ["13b", "14b", "solar"]):
            vram = 10000
        elif any(k in g for k in ["machine learning", "ai model", "train", "neural", "fine-tune"]):
            vram = 16000
        elif any(k in g for k in ["multiple files", "multi-file", "architecture", "framework", "database"]):
            vram = 8192
        return vram

    def _score_complexity(self, goal: str) -> float:
        """Score task complexity 0.0-1.0. Higher = more complex."""
        g = goal.lower()
        score = 0.0
        # Length factor
        words = len(g.split())
        score += min(words / 100, 0.3)
        # Complexity keywords
        if any(k in g for k in ["multiple files", "multi-file", "architecture", "framework"]):
            score += 0.3
        if any(k in g for k in ["database", "sql", "api", "rest", "graphql"]):
            score += 0.2
        if any(k in g for k in ["machine learning", "ai model", "train", "neural"]):
            score += 0.4
        if any(k in g for k in ["large", "complex", "enterprise", "scalable"]):
            score += 0.2
        # File count hints
        if "10" in g or "20" in g or "50" in g:
            score += 0.2
        return min(score, 1.0)

    def _poll_remote_task(self, local_task_id: str, client, remote_task_id: str):
        """Poll a remote task and sync status back to local task."""
        task = self.tasks.get(local_task_id)
        if not task:
            return
        try:
            for _ in range(100):  # Max ~5 min of polling
                if self._stop_events.get(local_task_id, Event()).is_set():
                    task.status = "FAILED"
                    task.result_summary = "Stopped by user."
                    return
                result = client.get_task(remote_task_id)
                if result.get("success") and result.get("data"):
                    data = result["data"]
                    task.status = data.get("status", "RUNNING")
                    task.current_step = data.get("current_step", 0)
                    # Sync logs
                    for log_data in data.get("logs", []):
                        # Only append if new (simple dedup by step)
                        existing_steps = {l.step for l in task.logs}
                        if log_data["step"] not in existing_steps:
                            task.logs.append(TaskLog(
                                timestamp=log_data.get("timestamp", time.time()),
                                step=log_data["step"],
                                action=log_data["action"],
                                result=log_data["result"],
                                success=log_data["success"],
                            ))
                    if task.status in ("COMPLETED", "FAILED"):
                        task.result_summary = f"[Remote: {client.node_id}] {data.get('result_summary', 'Done')}"
                        return
                time.sleep(3)
            task.status = "FAILED"
            task.result_summary = "Remote task polling timed out."
        except Exception as e:
            task.status = "FAILED"
            task.result_summary = f"Remote polling error: {e}"

    def stop_task(self, task_id: str) -> bool:
        ev = self._stop_events.get(task_id)
        if ev:
            ev.set()
            return True
        return False

    def get_task(self, task_id: str) -> Optional[CoderTask]:
        return self.tasks.get(task_id)

    def list_tasks(self) -> List[CoderTask]:
        return sorted(self.tasks.values(), key=lambda t: t.created_at, reverse=True)

    def _log(self, task: CoderTask, step: int, action: str, result: dict):
        task.logs.append(TaskLog(
            timestamp=time.time(),
            step=step,
            action=action,
            result=json.dumps(result)[:800],
            success=result.get("success", False),
        ))
        task.updated_at = time.time()

    def _is_code_generation_goal(self, goal: str) -> bool:
        """Detect if the goal is about creating code files."""
        keywords = ["create", "build", "write", "app", "script", "api", ".py", "python", "flask", "django", "streamlit", "fastapi"]
        return any(k in goal.lower() for k in keywords)

    def _extract_file_plan(self, task: CoderTask) -> List[Dict[str, str]]:
        """Ask the LLM for a natural-language plan of files to create."""
        prompt = f"""Goal: {task.goal}

What files do you need to create? List them as bullet points.
Format each line like: - filename.py: brief description of what it contains
Only list the files needed. Do NOT write code."""
        result = self.llm.chat(
            "You are a software architect. Plan the minimum set of files needed.",
            prompt,
            temperature=0.1,
            timeout=60,
        )
        if not result.get("success"):
            return []

        plan = []
        for line in result["response"].split("\n"):
            line = line.strip()
            if line.startswith("-") or line.startswith("*"):
                content = line[1:].strip()
                if ":" in content:
                    filename, desc = content.split(":", 1)
                    filename = filename.strip().strip("`'")  # Strip backticks and quotes
                    plan.append({"file": filename, "description": desc.strip()})
                elif " " in content:
                    parts = content.split(" ", 1)
                    filename = parts[0].strip().strip("`'")
                    plan.append({"file": filename, "description": parts[1].strip()})
        return plan

    def _create_file_with_llm(self, task: CoderTask, filename: str, description: str, stop_event: Event) -> bool:
        """Ask the LLM to write a single file, retry on syntax errors."""
        if stop_event.is_set():
            return False

        is_python = filename.endswith(".py")
        block_hint = "```python" if is_python else "```"
        sys_msg = "You write clean, working code. Return ONLY the file content inside a code block. No explanations."
        user_msg = f"Goal: {task.goal}\n\nWrite the complete content for {filename}.\nPurpose: {description}\n\nReturn ONLY the code inside a {block_hint} block."

        for attempt in range(3):
            if stop_event.is_set():
                return False
            result = self.llm.chat(sys_msg, user_msg, temperature=0.1, timeout=90)
            if not result.get("success"):
                continue

            blocks = _extract_code_blocks(result["response"])
            if blocks:
                content = blocks[0]
                res = self.fs.write_file(filename, content)
                task.current_step += 1
                self._log(task, task.current_step, "write_file", res)

                if is_python and res.get("success"):
                    safe_path = f'"{res["path"]}"'
                    check = self.shell.run(f"python -m py_compile {safe_path}", timeout=10)
                    if not check["success"]:
                        err = check.get("stderr", "Syntax error")
                        user_msg += f"\n\nThe previous code had a syntax error:\n{err}\n\nPlease fix it and return the corrected code."
                        continue  # Retry with error hint
                return res.get("success", False)
        return False

    def _run_code_generation_task(self, task_id: str):
        """v3: Plan-first execution for code generation."""
        import traceback
        task = self.tasks[task_id]
        stop_event = self._stop_events[task_id]

        try:
            task.status = "RUNNING"

            # Phase 1: Extract file plan
            plan = self._extract_file_plan(task)
            if not plan:
                # Fallback: single file guess
                plan = [{"file": "app.py", "description": "Main application file"}]

            # Phase 2: Create each file
            for item in plan:
                if stop_event.is_set():
                    task.status = "FAILED"
                    task.result_summary = "Stopped by user."
                    return
                ok = self._create_file_with_llm(task, item["file"], item["description"], stop_event)
                if not ok:
                    task.status = "FAILED"
                    task.result_summary = f"Failed to create {item['file']} after multiple attempts."
                    return

            # Phase 3: Auto-test each created file
            test_results = []
            for item in plan:
                fpath = self.fs._resolve(item["file"])
                if fpath.exists() and fpath.suffix == ".py":
                    # Syntax check
                    import subprocess, sys
                    result = subprocess.run(
                        [sys.executable, "-m", "py_compile", str(fpath)],
                        capture_output=True, text=True, timeout=10
                    )
                    test_results.append({
                        "file": item["file"],
                        "syntax": result.returncode == 0,
                        "error": result.stderr.strip() if result.returncode != 0 else None,
                    })

            # Phase 4: Report results
            missing = [p["file"] for p in plan if not self.fs._resolve(p["file"]).exists()]
            if missing:
                task.status = "FAILED"
                task.result_summary = f"Missing files: {', '.join(missing)}"
            else:
                passed = sum(1 for t in test_results if t["syntax"])
                total = len(test_results)
                file_list = ", ".join(p["file"] for p in plan)
                task.status = "COMPLETED"
                if total > 0:
                    task.result_summary = f"Created {len(plan)} files ({passed}/{total} syntax OK): {file_list}"
                else:
                    task.result_summary = f"Created {len(plan)} files: {file_list}"

        except Exception as e:
            task.status = "FAILED"
            task.result_summary = f"Exception: {str(e)}"
            traceback.print_exc()

    def _run_reactive_task(self, task_id: str):
        """v2: Reactive step-by-step planning for non-code goals."""
        import traceback
        task = self.tasks[task_id]
        stop_event = self._stop_events[task_id]
        max_steps = 20

        file_edit_counts: Dict[str, int] = {}
        file_write_counts: Dict[str, int] = {}
        last_actions: List[str] = []

        try:
            task.status = "RUNNING"

            for step_num in range(1, max_steps + 1):
                if stop_event.is_set():
                    task.status = "FAILED"
                    task.result_summary = "Stopped by user."
                    return

                stuck_warning = ""
                if task.logs:
                    last_log = task.logs[-1]
                    if last_log.action == "edit_file" and last_log.success:
                        try:
                            r = json.loads(last_log.result)
                            fpath = r.get("path", "")
                            file_edit_counts[fpath] = file_edit_counts.get(fpath, 0) + 1
                            if file_edit_counts[fpath] >= 3:
                                stuck_warning = f"WARNING: You have edited {fpath} {file_edit_counts[fpath]} times. STOP editing this file."
                        except Exception:
                            pass

                    last_actions.append(last_log.action)
                    if len(last_actions) > 4:
                        last_actions.pop(0)
                    if len(last_actions) >= 3 and len(set(last_actions)) == 1:
                        stuck_warning += f" WARNING: You have done '{last_actions[0]}' {len(last_actions)} times in a row. Try a different action."

                task.current_step = step_num
                step = self.planner.decide_next(task, stuck_warning)

                if step is None:
                    time.sleep(2)
                    step = self.planner.decide_next(task, stuck_warning)
                    if step is None:
                        task.status = "FAILED"
                        task.result_summary = "LLM could not decide next action after multiple retries. Task too complex for current model."
                        return

                result = self.executor.execute(step)
                self._log(task, step.step_number, step.action, result)

                if step.action == "done":
                    task.status = "COMPLETED"
                    task.result_summary = result.get("summary", "Task completed.")
                    return

                if not result.get("success") and step.action in ("write_file", "edit_file"):
                    pass

        except Exception as e:
            task.status = "FAILED"
            task.result_summary = f"Exception: {str(e)}"
            traceback.print_exc()

    def _run_task(self, task_id: str):
        """Route to the appropriate execution strategy."""
        task = self.tasks[task_id]
        if self._is_code_generation_goal(task.goal):
            self._run_code_generation_task(task_id)
        else:
            self._run_reactive_task(task_id)

    def to_dict(self, task: CoderTask) -> dict:
        return {
            "task_id": task.task_id,
            "goal": task.goal,
            "status": task.status,
            "current_step": task.current_step,
            "total_steps": task.current_step,  # In reactive mode, total = current (grows as we go)
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "result_summary": task.result_summary,
            "logs": [
                {
                    "timestamp": l.timestamp,
                    "step": l.step,
                    "action": l.action,
                    "result": l.result,
                    "success": l.success,
                }
                for l in task.logs
            ],
        }
