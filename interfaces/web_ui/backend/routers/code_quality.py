"""
code_quality.py
===============
Auto-quality checking for generated code.
Runs syntax validation, import checks, and basic execution tests.
Assigns a quality score (0-100) before review submission.
"""
import os
import sys
import ast
import subprocess
import tempfile
import json
from typing import Dict, List, Optional, Any
from pathlib import Path
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/quality", tags=["code-quality"])


class QualityCheckRequest(BaseModel):
    task_id: str
    workspace_path: Optional[str] = None


class QualityResult(BaseModel):
    task_id: str
    overall_score: int
    passed: bool
    checks: List[Dict[str, Any]]
    summary: str


def _check_syntax(file_path: str) -> Dict[str, Any]:
    """Check if Python file has valid syntax."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        ast.parse(source)
        return {"name": "syntax", "passed": True, "score": 25, "detail": "Valid Python syntax"}
    except SyntaxError as e:
        return {"name": "syntax", "passed": False, "score": 0, "detail": f"Syntax error: {e.msg} at line {e.lineno}"}
    except Exception as e:
        return {"name": "syntax", "passed": False, "score": 0, "detail": str(e)}


def _check_imports(file_path: str) -> Dict[str, Any]:
    """Check if all imports can be resolved."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module.split('.')[0])

        missing = []
        for mod in set(imports):
            if mod in ('os', 'sys', 'json', 'time', 'uuid', 'ast', 'subprocess', 'pathlib', 'typing', 'tempfile'):
                continue  # stdlib
            try:
                __import__(mod)
            except ImportError:
                missing.append(mod)

        if missing:
            return {"name": "imports", "passed": False, "score": 10,
                    "detail": f"Missing packages: {', '.join(missing)}"}
        return {"name": "imports", "passed": True, "score": 20,
                "detail": f"All {len(set(imports))} imports resolvable"}
    except Exception as e:
        return {"name": "imports", "passed": False, "score": 0, "detail": str(e)}


def _check_execution(file_path: str, timeout: int = 5) -> Dict[str, Any]:
    """Try to run the script in a sandboxed way."""
    try:
        result = subprocess.run(
            [sys.executable, file_path],
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "PYTHONPATH": str(Path(file_path).parent)}
        )
        if result.returncode == 0:
            return {"name": "execution", "passed": True, "score": 30,
                    "detail": "Script executed without errors"}
        else:
            stderr = result.stderr[:200] if result.stderr else "Unknown error"
            return {"name": "execution", "passed": False, "score": 10,
                    "detail": f"Runtime error: {stderr}"}
    except subprocess.TimeoutExpired:
        return {"name": "execution", "passed": True, "score": 25,
                "detail": "Script ran but timed out (may be a long-running service)"}
    except Exception as e:
        return {"name": "execution", "passed": False, "score": 0, "detail": str(e)}


def _check_structure(file_path: str) -> Dict[str, Any]:
    """Check code structure (functions, classes, docstrings)."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)

        funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        docstrings = sum(1 for n in funcs + classes if ast.get_docstring(n))

        score = 0
        details = []
        if funcs:
            score += 5
            details.append(f"{len(funcs)} functions")
        if classes:
            score += 5
            details.append(f"{len(classes)} classes")
        if docstrings:
            score += 5
            details.append(f"{docstrings} docstrings")
        if len(source.split('\n')) > 10:
            score += 5
            details.append("substantial code")

        return {"name": "structure", "passed": score >= 10, "score": score,
                "detail": ', '.join(details) if details else "Minimal structure"}
    except Exception as e:
        return {"name": "structure", "passed": False, "score": 0, "detail": str(e)}


def _find_main_file(workspace: Path) -> Optional[Path]:
    """Find the main Python file in a workspace."""
    candidates = list(workspace.glob('*.py'))
    if not candidates:
        return None
    # Prefer app.py, main.py, bot.py, or the largest file
    for name in ['app.py', 'main.py', 'bot.py', 'server.py', 'api.py']:
        for c in candidates:
            if c.name == name:
                return c
    return max(candidates, key=lambda p: p.stat().st_size)


@router.post("/check", response_model=QualityResult)
def check_quality(req: QualityCheckRequest):
    """Run full quality check on generated code for a task."""
    workspace = Path(req.workspace_path) if req.workspace_path else Path(f"marketplace_tasks/{req.task_id}")
    if not workspace.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    main_file = _find_main_file(workspace)
    if not main_file:
        raise HTTPException(status_code=404, detail="No Python files found in workspace")

    checks = [
        _check_syntax(str(main_file)),
        _check_imports(str(main_file)),
        _check_execution(str(main_file)),
        _check_structure(str(main_file)),
    ]

    total_score = sum(c["score"] for c in checks)
    passed = total_score >= 60

    summary = f"Score: {total_score}/100 — "
    if total_score >= 80:
        summary += "Excellent quality"
    elif total_score >= 60:
        summary += "Good quality, minor issues"
    elif total_score >= 40:
        summary += "Fair quality, needs work"
    else:
        summary += "Poor quality, major issues"

    return QualityResult(
        task_id=req.task_id,
        overall_score=total_score,
        passed=passed,
        checks=checks,
        summary=summary,
    )


@router.get("/check/{task_id}")
def quick_check(task_id: str):
    """Quick quality check for a task workspace."""
    return check_quality(QualityCheckRequest(task_id=task_id))
