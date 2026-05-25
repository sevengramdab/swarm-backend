"""
projects.py
===========
Project discovery, testing, and launcher for SwarmCoder-generated apps.
Integrates into the SimpleSwarm dashboard.
"""
from __future__ import annotations

import os
import json
import time
import subprocess
import sys
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/projects", tags=["projects"])

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent.resolve()
_RUNNING: Dict[str, Dict[str, Any]] = {}


def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _find_free_port(start: int = 8600) -> int:
    port = start
    while not _is_port_free(port):
        port += 1
    return port


def _detect_type(filepath: Path) -> str:
    text = filepath.read_text(encoding="utf-8", errors="ignore").lower()
    if "import streamlit" in text or "from streamlit" in text:
        return "streamlit"
    if "from flask" in text or "import flask" in text:
        return "flask"
    if "from fastapi" in text or "import fastapi" in text:
        return "fastapi"
    if "import argparse" in text:
        return "cli"
    return "script"


def _scan_projects() -> List[Dict[str, Any]]:
    projects = []
    exclude = {"project_launcher.py", "conftest.py", "test_harness.py"}
    for f in sorted(_PROJECT_ROOT.glob("*.py")):
        if f.name in exclude or f.name.startswith("test_"):
            continue
        stat = f.stat()
        lines = len(f.read_text(encoding="utf-8", errors="ignore").splitlines())
        proj_type = _detect_type(f)
        projects.append({
            "name": f.stem,
            "file": f.name,
            "type": proj_type,
            "lines": lines,
            "size_kb": round(stat.st_size / 1024, 1),
            "created": time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_ctime)),
            "running": f.name in _RUNNING,
            "port": _RUNNING.get(f.name, {}).get("port"),
        })
    return projects


def _test_syntax(filepath: Path) -> Dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(filepath)],
        capture_output=True, text=True, timeout=10
    )
    return {
        "test": "syntax",
        "passed": result.returncode == 0,
        "error": result.stderr.strip() if result.returncode != 0 else None,
    }


def _test_imports(filepath: Path) -> Dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_PROJECT_ROOT)
    result = subprocess.run(
        [sys.executable, "-c", f"import importlib; importlib.import_module('{filepath.stem}')"],
        capture_output=True, text=True, timeout=15,
        cwd=str(_PROJECT_ROOT), env=env
    )
    return {
        "test": "imports",
        "passed": result.returncode == 0,
        "error": result.stderr.strip() if result.returncode != 0 else None,
    }


def _test_cli_help(filepath: Path) -> Dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(filepath), "--help"],
        capture_output=True, text=True, timeout=10
    )
    return {
        "test": "cli_help",
        "passed": result.returncode == 0 and len(result.stdout) > 50,
        "error": result.stderr.strip() if result.returncode != 0 else None,
    }


def _test_flask_endpoints(filepath: Path, port: int = 8765) -> Dict[str, Any]:
    text = filepath.read_text(encoding="utf-8", errors="ignore")
    if "Flask(" not in text:
        return {"test": "flask_endpoints", "passed": None, "error": "Not a Flask app"}

    proc = subprocess.Popen(
        [sys.executable, str(filepath)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=str(_PROJECT_ROOT)
    )
    time.sleep(4)
    ok = False
    errors = []
    try:
        import urllib.request
        for path in ["/tasks", "/"]:
            try:
                req = urllib.request.Request(f"http://127.0.0.1:5000{path}", method="GET")
                resp = urllib.request.urlopen(req, timeout=5)
                if resp.status in (200, 404):
                    ok = True
                    break
            except Exception as e:
                errors.append(f"{path}: {e}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except:
            proc.kill()

    return {
        "test": "flask_endpoints",
        "passed": ok,
        "error": "; ".join(errors) if errors else None,
    }


@router.get("/")
async def list_projects():
    """List all discovered Python projects."""
    return {"projects": _scan_projects()}


@router.get("/{name}/test")
async def test_project(name: str):
    """Run the full test suite on a single project file."""
    filepath = _PROJECT_ROOT / name
    if not filepath.exists() or not filepath.suffix == ".py":
        raise HTTPException(status_code=404, detail=f"Project {name} not found")

    results = [_test_syntax(filepath)]
    proj_type = _detect_type(filepath)

    if proj_type == "flask":
        results.append(_test_flask_endpoints(filepath))
    elif proj_type == "cli":
        results.append(_test_cli_help(filepath))
    else:
        results.append(_test_imports(filepath))

    passed = sum(1 for r in results if r["passed"] is True)
    failed = sum(1 for r in results if r["passed"] is False)
    return {
        "name": name,
        "type": proj_type,
        "results": results,
        "passed": passed,
        "failed": failed,
        "total": len(results),
    }


class LaunchRequest(BaseModel):
    port: Optional[int] = None


@router.post("/{name}/launch")
async def launch_project(name: str, req: LaunchRequest):
    """Launch a project on an available port."""
    filepath = _PROJECT_ROOT / name
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Project {name} not found")

    if name in _RUNNING:
        return {"success": True, "message": "Already running", "port": _RUNNING[name]["port"], "url": _RUNNING[name]["url"]}

    port = req.port or _find_free_port()
    proj_type = _detect_type(filepath)
    cmd = None

    if proj_type == "streamlit":
        cmd = [sys.executable, "-m", "streamlit", "run", str(filepath),
               "--server.port", str(port), "--server.headless", "true",
               "--browser.gatherUsageStats", "false"]
    elif proj_type in ("flask", "fastapi"):
        cmd = [sys.executable, str(filepath)]
    else:
        return {"success": False, "message": f"Cannot auto-launch {proj_type} projects. Run manually: python {name}"}

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(_PROJECT_ROOT))
        time.sleep(3)
        _RUNNING[name] = {
            "port": port,
            "pid": proc.pid,
            "started": time.time(),
            "url": f"http://localhost:{port}",
            "type": proj_type,
        }
        return {"success": True, "message": f"Launched on port {port}", "port": port, "url": _RUNNING[name]["url"]}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/{name}/stop")
async def stop_project(name: str):
    """Stop a running project."""
    if name not in _RUNNING:
        raise HTTPException(status_code=404, detail=f"Project {name} is not running")

    info = _RUNNING[name]
    try:
        import psutil
        proc = psutil.Process(info["pid"])
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        pass
    del _RUNNING[name]
    return {"success": True, "message": f"Stopped {name}"}


@router.get("/running")
async def running_projects():
    """List all currently running projects."""
    return {"running": _RUNNING}
