"""
Project Launcher — SwarmCoder Project Hub
==========================================
A Streamlit dashboard that discovers, catalogs, and launches
all Python projects created by SwarmCoder.
"""

import streamlit as st
import subprocess
import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
import socket

PROJECT_ROOT = Path(__file__).parent.resolve()
EXCLUDE = {"project_launcher.py", "test_*.py", "*_test.py", "conftest.py"}


def is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def find_free_port(start: int = 8600) -> int:
    port = start
    while not is_port_free(port):
        port += 1
    return port


def detect_project_type(filepath: Path) -> str:
    text = filepath.read_text(encoding="utf-8", errors="ignore").lower()
    if "import streamlit" in text or "from streamlit" in text:
        return "Streamlit"
    if "from flask" in text or "import flask" in text:
        return "Flask"
    if "from fastapi" in text or "import fastapi" in text:
        return "FastAPI"
    if "import argparse" in text:
        return "CLI"
    return "Script"


def scan_projects() -> list:
    projects = []
    for f in sorted(PROJECT_ROOT.glob("*.py")):
        if any(f.name.startswith(p.replace("*.py", "")) for p in EXCLUDE if "*" in p):
            continue
        if f.name in EXCLUDE:
            continue
        stat = f.stat()
        lines = len(f.read_text(encoding="utf-8", errors="ignore").splitlines())
        projects.append({
            "name": f.stem,
            "file": str(f.name),
            "path": str(f),
            "type": detect_project_type(f),
            "lines": lines,
            "size_kb": round(stat.st_size / 1024, 1),
            "created": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M"),
        })
    return projects


def get_running_apps() -> dict:
    """Load running apps from session state."""
    if "running_apps" not in st.session_state:
        st.session_state.running_apps = {}
    return st.session_state.running_apps


def launch_app(project: dict):
    running = get_running_apps()
    if project["file"] in running:
        st.warning(f"{project['name']} is already running on port {running[project['file']]['port']}")
        return

    port = find_free_port()
    cmd = None

    if project["type"] == "Streamlit":
        cmd = [sys.executable, "-m", "streamlit", "run", project["path"],
               "--server.port", str(port), "--server.headless", "true",
               "--browser.gatherUsageStats", "false"]
    elif project["type"] in ("Flask", "FastAPI"):
        env = os.environ.copy()
        env["FLASK_RUN_PORT"] = str(port)
        # For Flask apps, just run the python file directly
        cmd = [sys.executable, project["path"]]
    elif project["type"] == "CLI":
        st.info(f"{project['name']} is a CLI app. Run it manually with: `python {project['file']} --help`")
        return
    else:
        cmd = [sys.executable, project["path"]]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(PROJECT_ROOT))
        time.sleep(3)  # Give it time to start
        running[project["file"]] = {
            "port": port,
            "pid": proc.pid,
            "started": datetime.now().strftime("%H:%M:%S"),
            "url": f"http://localhost:{port}",
        }
        st.session_state.running_apps = running
        st.success(f"Launched {project['name']} on port {port}")
    except Exception as e:
        st.error(f"Failed to launch: {e}")


def stop_app(project: dict):
    running = get_running_apps()
    if project["file"] not in running:
        st.warning("Not running")
        return
    info = running[project["file"]]
    try:
        import psutil
        proc = psutil.Process(info["pid"])
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        pass
    del running[project["file"]]
    st.session_state.running_apps = running
    st.success(f"Stopped {project['name']}")


def type_color(t: str) -> str:
    return {
        "Streamlit": "🔴",
        "Flask": "🟢",
        "FastAPI": "🔵",
        "CLI": "⚪",
        "Script": "🟡",
    }.get(t, "⚫")


st.set_page_config(page_title="SwarmCoder Project Hub", layout="wide")
st.title("🚀 SwarmCoder Project Hub")
st.caption("Discover and launch everything SwarmCoder has built for you.")

projects = scan_projects()
running = get_running_apps()

st.subheader(f"Projects ({len(projects)} found)")

for i in range(0, len(projects), 3):
    cols = st.columns(3)
    for j, proj in enumerate(projects[i:i + 3]):
        with cols[j]:
            is_running = proj["file"] in running
            status = "🟢 Running" if is_running else "⚪ Stopped"
            url = running[proj["file"]]["url"] if is_running else None

            with st.container(border=True):
                st.markdown(f"### {type_color(proj['type'])} {proj['name']}")
                st.caption(f"{proj['type']} • {proj['lines']} lines • {proj['size_kb']} KB")
                st.caption(f"Created: {proj['created']}")

                if is_running and url:
                    st.markdown(f"**Status:** {status} on `: {running[proj['file']]['port']}`")
                    st.link_button("🔗 Open in Browser", url)
                    if st.button("⏹ Stop", key=f"stop_{proj['file']}"):
                        stop_app(proj)
                        st.rerun()
                else:
                    st.markdown(f"**Status:** {status}")
                    if st.button("▶ Launch", key=f"launch_{proj['file']}"):
                        launch_app(proj)
                        st.rerun()

st.divider()
st.caption("Projects are auto-discovered from `.py` files in the project root. Refresh the page to update.")
