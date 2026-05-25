"""
delegate.py
===========
AI Assistant → SwarmCoder delegation bridge.
When the user asks for code/build tasks, submit to SwarmCoder instead
of doing it manually. This reduces token usage dramatically.

Usage:
    python delegate.py "Create a script that..."
"""
import urllib.request
import json
import time
import sys

API = "http://localhost:8000"

def submit(goal: str) -> str:
    payload = json.dumps({"goal": goal}).encode()
    req = urllib.request.Request(f"{API}/swarmcoder/task", data=payload,
                                  headers={"Content-Type": "application/json"}, method="POST")
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())["task_id"]

def poll(task_id: str, timeout_sec: int = 300):
    start = time.time()
    seen = 0
    print(f"[Delegate] Task {task_id} submitted. Polling...", flush=True)
    while time.time() - start < timeout_sec:
        req = urllib.request.Request(f"{API}/swarmcoder/task/{task_id}", method="GET")
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        # Print new logs
        for log in data["logs"][seen:]:
            seen += 1
            ok = "OK" if log["success"] else "FAIL"
            print(f"  Step {log['step']:2d}: {log['action']:12s} {ok}", flush=True)
        status = data["status"]
        if status in ("COMPLETED", "FAILED"):
            print(f"[Delegate] {status}: {data['result_summary']}", flush=True)
            return data
        time.sleep(3)
    print("[Delegate] Timeout", flush=True)
    return None

if __name__ == "__main__":
    goal = sys.argv[1] if len(sys.argv) > 1 else "Say hello"
    task_id = submit(goal)
    result = poll(task_id)
    sys.exit(0 if result and result["status"] == "COMPLETED" else 1)
