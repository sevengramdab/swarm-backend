#!/usr/bin/env python3
"""
kimi_resume.py
==============
CLI companion that monitors the SimplePod Swarm and auto-resumes
connections after VS Code reloads or backend restarts.

ELI5: Like a building's emergency generator auto-start controller.
       When the grid goes down (VS Code reloads), it senses the outage,
       waits 3 seconds, then fires up the generator and transfers the
       load back automatically. Nobody in the building even notices
       the lights flickered.

Usage:
    python scripts/kimi_resume.py           # Monitor mode
    python scripts/kimi_resume.py --once    # Single health check
    python scripts/kimi_resume.py --restart # Kill and restart backend
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Default config
# ---------------------------------------------------------------------------
DEFAULT_API_URL = "http://localhost:8000"
CHECK_INTERVAL = 5.0  # seconds
RESTART_DELAY = 3.0   # seconds after detecting outage


class ResumeMonitor:
    """
    The auto-transfer switch brain.

    ELI5: Like the automatic transfer switch (ATS) in a hospital.
          It watches the utility line (backend) with a voltmeter
          (HTTP health check). If voltage drops to zero, it waits
          a moment (in case it's just a brief sag), then snaps the
          contactors to generator power (restarts the backend).
    """

    def __init__(self, api_url: str = DEFAULT_API_URL) -> None:
        self.api_url = api_url.rstrip("/")
        self.consecutive_failures = 0
        self.failure_threshold = 2  # How many misses before we declare outage
        self.was_healthy = True

    def check_health(self) -> bool:
        """
        Knock on the electrical room door and ask "you alive?"
        Returns True if the backend responds with healthy status.
        """
        try:
            req = urllib.request.Request(
                f"{self.api_url}/health",
                method="GET",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("status") == "healthy"
        except Exception:
            return False

    def restart_backend(self) -> bool:
        """
        ELI5: The main breaker tripped. Walk to the panel, reset the
              breaker, and flip it back on. Then check the lights.
        """
        print("[RESUME] Backend appears down. Attempting restart...")
        import os
        import subprocess

        swarm_root = Path(__file__).parent.parent.resolve()
        venv_python = swarm_root / ".venv" / "Scripts" / "python.exe"
        if not venv_python.exists():
            venv_python = swarm_root / ".venv" / "bin" / "python"
        if not venv_python.exists():
            venv_python = Path(sys.executable)

        # Try to kill any existing uvicorn on port 8000
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["powershell", "-Command", "Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"],
                    capture_output=True,
                )
            else:
                subprocess.run(
                    ["bash", "-c", "lsof -ti:8000 | xargs kill -9 2>/dev/null || true"],
                    capture_output=True,
                )
        except Exception:
            pass

        time.sleep(1)

        # Start fresh uvicorn process
        try:
            subprocess.Popen(
                [
                    str(venv_python), "-m", "uvicorn",
                    "interfaces.web_ui.backend.main:app",
                    "--host", "0.0.0.0",
                    "--port", "8000",
                ],
                cwd=str(swarm_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print("[RESUME] Backend restart initiated.")
            return True
        except Exception as exc:
            print(f"[RESUME] Restart failed: {exc}")
            return False

    def run_monitor(self) -> None:
        """
        ELI5: The night-shift security guard. Walks the building every
              5 minutes, checks every door lock, and calls maintenance
              if anything looks wrong. Never sleeps.
        """
        print(f"[RESUME] Kimi Auto-Resume Monitor started — watching {self.api_url}")
        print("[RESUME] Press Ctrl+C to stop.\n")

        while True:
            healthy = self.check_health()

            if healthy:
                if not self.was_healthy:
                    print("[RESUME] ✅ Backend is back online.")
                self.consecutive_failures = 0
                self.was_healthy = True
            else:
                self.consecutive_failures += 1
                self.was_healthy = False
                print(
                    f"[RESUME] ⚠️ Backend miss {self.consecutive_failures}/"
                    f"{self.failure_threshold}"
                )

                if self.consecutive_failures >= self.failure_threshold:
                    print("[RESUME] 🔥 Outage confirmed. Initiating auto-resume...")
                    time.sleep(RESTART_DELAY)
                    if self.restart_backend():
                        # Give it time to boot before next check
                        time.sleep(5)
                    self.consecutive_failures = 0

            time.sleep(CHECK_INTERVAL)

    def run_once(self) -> bool:
        """Single health check — returns True if backend is up."""
        healthy = self.check_health()
        print(f"[RESUME] Health check: {'✅ HEALTHY' if healthy else '❌ DOWN'}")
        return healthy


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Kimi Auto-Resume — Monitor and auto-restart SimplePod Swarm"
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Backend API URL")
    parser.add_argument("--once", action="store_true", help="Single check, then exit")
    parser.add_argument("--restart", action="store_true", help="Force restart backend now")
    args = parser.parse_args()

    monitor = ResumeMonitor(api_url=args.api_url)

    if args.restart:
        monitor.restart_backend()
        sys.exit(0)

    if args.once:
        ok = monitor.run_once()
        sys.exit(0 if ok else 1)

    try:
        monitor.run_monitor()
    except KeyboardInterrupt:
        print("\n[RESUME] Monitor stopped by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
