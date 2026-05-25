"""
test_distributed.py
===================
End-to-end test for SimplePod distributed task routing.

Usage:
    python test_distributed.py

What it tests:
1. Starts a mock remote SimplePod node on port 8001
2. Registers it with the local mesh (port 8000)
3. Submits a COMPLEX task that should trigger remote routing
4. Verifies the task is forwarded to the remote node
5. Polls both local and remote tasks until completion
6. Asserts results match and files were created
7. Stops the remote node and deregisters it

Exit codes:
    0 = all tests passed
    1 = test failed
"""
from __future__ import annotations

import subprocess
import sys
import time
import json
import urllib.request
import signal
import os
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────
LOCAL_URL = "http://localhost:8000"
REMOTE_URL = "http://localhost:8001"
REMOTE_PORT = 8001
REMOTE_SCRIPT = Path(__file__).parent / "remote_node.py"
MAX_WAIT_SECONDS = 180
POLL_INTERVAL = 3

# A goal complex enough to trigger remote routing (complexity >= 0.6)
COMPLEX_GOAL = (
    "build a complex multi-file machine learning pipeline with data preprocessing, "
    "model training, evaluation metrics, and REST API deployment using Flask and scikit-learn"
)


# ── HTTP helpers ───────────────────────────────────────────────────────────

def api_get(base: str, path: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(f"{base}{path}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def api_post(base: str, path: str, body: dict, timeout: int = 10) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"{base}{path}", data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


# ── Test runner ────────────────────────────────────────────────────────────

class DistributedTest:
    def __init__(self):
        self.remote_proc: subprocess.Popen | None = None
        self.local_task_id: str | None = None
        self.remote_task_id: str | None = None
        self.passed = 0
        self.failed = 0

    def _check(self, condition: bool, msg: str):
        if condition:
            print(f"  PASS {msg}")
            self.passed += 1
        else:
            print(f"  FAIL {msg}")
            self.failed += 1

    def start_remote_node(self):
        print("\n>> Starting remote node...")
        self.remote_proc = subprocess.Popen(
            [sys.executable, str(REMOTE_SCRIPT)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(Path(__file__).parent),
        )
        # Wait for it to be ready
        for _ in range(20):
            time.sleep(1)
            try:
                health = api_get(REMOTE_URL, "/health", timeout=2)
                if health.get("status") == "healthy":
                    print(f"  Remote node ready (PID {self.remote_proc.pid})")
                    return
            except Exception:
                continue
        raise RuntimeError("Remote node failed to start")

    def stop_remote_node(self):
        print("\n>> Stopping remote node...")
        if self.remote_proc:
            self.remote_proc.terminate()
            try:
                self.remote_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.remote_proc.kill()
        # Deregister from mesh
        try:
            api_post(LOCAL_URL, "/mesh/nodes/discover", {}, timeout=5)
        except Exception:
            pass
        print("  Remote node stopped")

    def register_remote_node(self):
        print("\n>> Registering remote node with mesh...")
        result = api_post(LOCAL_URL, "/mesh/nodes/register", {
            "node_id": "remote-test-01",
            "name": "Test Remote Node",
            "endpoint": REMOTE_URL,
            "tier": "cloud",
            "models": ["llama3.2", "dolphin-llama3"],
        })
        self._check(result.get("success") is True, f"Node registered: {result.get('message', '')}")
        self._check(result.get("healthy") is True, "Remote node health check passed")

    def verify_mesh_topology(self):
        print("\n>> Verifying mesh topology...")
        topo = api_get(LOCAL_URL, "/mesh/topology", timeout=10)
        nodes = topo.get("nodes", [])
        self._check(len(nodes) >= 1, f"Mesh has {len(nodes)} remote node(s)")
        remote = next((n for n in nodes if n["node_id"] == "remote-test-01"), None)
        self._check(remote is not None, "remote-test-01 found in mesh")
        if remote:
            self._check(remote["status"] == "online", f"Remote node is online ({remote.get('latency_ms', 0):.0f}ms)")
            self._check(remote["tier"] == "cloud", "Remote node tier is cloud")

    def submit_complex_task(self):
        print("\n>> Submitting complex task (should route to remote)...")
        result = api_post(LOCAL_URL, "/swarmcoder/task", {"goal": COMPLEX_GOAL})
        self.local_task_id = result.get("task_id")
        self._check(self.local_task_id is not None, f"Local task created: {self.local_task_id}")

        # Check if it was routed
        summary = result.get("result_summary", "")
        routed = "Routed to remote node" in summary
        self._check(routed, f"Task was routed to remote node: {summary[:80]}")

        if routed:
            # Extract remote task ID from summary
            import re
            m = re.search(r"task ([a-f0-9]+)", summary)
            if m:
                self.remote_task_id = m.group(1)
                print(f"  Remote task ID: {self.remote_task_id}")

    def poll_until_done(self):
        print("\n>> Polling tasks until completion...")
        start = time.time()
        while time.time() - start < MAX_WAIT_SECONDS:
            # Poll local task
            local = api_get(LOCAL_URL, f"/swarmcoder/task/{self.local_task_id}")
            local_status = local.get("status", "UNKNOWN")

            # Poll remote task
            if self.remote_task_id:
                try:
                    remote = api_get(REMOTE_URL, f"/swarmcoder/task/{self.remote_task_id}")
                    remote_status = remote.get("status", "UNKNOWN")
                    remote_summary = remote.get("result_summary", "")
                except Exception as e:
                    remote_status = f"error: {e}"
                    remote_summary = ""
            else:
                remote_status = "unknown"
                remote_summary = ""

            print(f"  Local: {local_status} | Remote: {remote_status} | Elapsed: {int(time.time()-start)}s")

            if local_status in ("COMPLETED", "FAILED"):
                self._check(local_status == "COMPLETED", f"Local task completed: {local.get('result_summary','')[:100]}")
                if self.remote_task_id:
                    self._check("Created" in remote_summary or "syntax OK" in remote_summary,
                                f"Remote task produced files: {remote_summary[:100]}")
                return

            time.sleep(POLL_INTERVAL)

        self._check(False, f"Task did not complete within {MAX_WAIT_SECONDS}s")

    def verify_remote_workspace(self):
        print("\n>> Verifying remote workspace files...")
        workspace = Path(__file__).parent / "remote_workspace"
        py_files = list(workspace.glob("*.py"))
        self._check(len(py_files) >= 3, f"Remote workspace has {len(py_files)} Python files")
        for f in py_files[:5]:
            print(f"    - {f.name}")

    def run(self) -> int:
        print("=" * 60)
        print("SimplePod Distributed Routing Test")
        print("=" * 60)

        try:
            self.start_remote_node()
            self.register_remote_node()
            self.verify_mesh_topology()
            self.submit_complex_task()
            self.poll_until_done()
            self.verify_remote_workspace()
        except Exception as e:
            print(f"\nERROR Test error: {e}")
            import traceback
            traceback.print_exc()
            self.failed += 1
        finally:
            self.stop_remote_node()

        print("\n" + "=" * 60)
        print(f"Results: {self.passed} passed, {self.failed} failed")
        print("=" * 60)
        return 0 if self.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(DistributedTest().run())
