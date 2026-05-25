"""
remote_client.py
================
HTTP client for forwarding SwarmCoder tasks to remote SimplePod nodes.

ELI5: When your house's solar panels can't handle the AC compressor,
      this is the phone call to the utility company asking them to
      spin up a gas turbine for you.
"""
from __future__ import annotations

import json
import urllib.request
import time
from typing import Optional, Dict, Any


class RemoteNodeClient:
    """Client for talking to another SimplePod instance."""

    def __init__(self, base_url: str, node_id: str, name: str = "", tier: str = "shadow"):
        self.base_url = base_url.rstrip("/")
        self.node_id = node_id
        self.name = name or node_id
        self.tier = tier
        self._last_health_check = 0.0
        self._healthy = False
        self._latency_ms = 9999.0
        self._models: list[str] = []

    def _request(self, method: str, path: str, body: Optional[dict] = None, timeout: int = 30) -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("X-SimplePod-Node", self.node_id)
        start = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                self._latency_ms = round((time.time() - start) * 1000, 1)
                return {"success": True, "status": resp.status, "data": json.loads(resp.read())}
        except Exception as e:
            self._latency_ms = 9999.0
            return {"success": False, "error": str(e)}

    def health_check(self) -> bool:
        """Ping the remote node. Returns True if alive."""
        result = self._request("GET", "/health", timeout=5)
        self._healthy = result.get("success") and result.get("data", {}).get("status") == "healthy"
        self._last_health_check = time.time()
        if self._healthy and result.get("data", {}).get("models"):
            self._models = result["data"]["models"]
        return self._healthy

    def submit_task(self, goal: str) -> dict:
        """Forward a SwarmCoder task to the remote node."""
        return self._request("POST", "/swarmcoder/task", {"goal": goal}, timeout=30)

    def get_task(self, task_id: str) -> dict:
        """Poll remote task status."""
        return self._request("GET", f"/swarmcoder/task/{task_id}", timeout=10)

    def list_models(self) -> dict:
        """Ask remote node what Ollama models it has."""
        return self._request("GET", "/simpleswarm/nodes/models", timeout=10)

    def get_metrics(self) -> dict:
        """Get remote node compute metrics."""
        return self._request("GET", "/simpleswarm/nodes/metrics", timeout=10)

    @property
    def is_healthy(self) -> bool:
        if time.time() - self._last_health_check > 30:
            return False
        return self._healthy

    @property
    def latency_ms(self) -> float:
        return self._latency_ms

    @property
    def models(self) -> list[str]:
        return self._models

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "endpoint": self.base_url,
            "tier": self.tier,
            "status": "online" if self.is_healthy else "offline",
            "latency_ms": self._latency_ms if self.is_healthy else 9999,
            "last_seen": self._last_health_check,
            "models": self._models,
        }


class RemoteNodePool:
    """Pool of known remote SimplePod nodes."""

    def __init__(self):
        self.nodes: Dict[str, RemoteNodeClient] = {}
        self._local_task_count = 0
        self._remote_task_count = 0

    def register(self, node_id: str, base_url: str, name: str = "", tier: str = "shadow") -> RemoteNodeClient:
        client = RemoteNodeClient(base_url, node_id, name=name, tier=tier)
        self.nodes[node_id] = client
        return client

    def deregister(self, node_id: str) -> bool:
        return self.nodes.pop(node_id, None) is not None

    def get_healthy_nodes(self) -> list:
        return [c for c in self.nodes.values() if c.health_check()]

    def get_best_node(self, prefer_large_model: bool = False) -> Optional[RemoteNodeClient]:
        """Pick the best available remote node."""
        healthy = self.get_healthy_nodes()
        if not healthy:
            return None
        # Sort by latency, prefer cloud tier for large models
        if prefer_large_model:
            cloud = [c for c in healthy if c.tier == "cloud"]
            if cloud:
                return min(cloud, key=lambda x: x.latency_ms)
        return min(healthy, key=lambda x: x.latency_ms)

    def health_summary(self) -> list:
        return [c.to_dict() for c in self.nodes.values()]

    def record_local_task(self):
        self._local_task_count += 1

    def record_remote_task(self):
        self._remote_task_count += 1

    @property
    def local_task_count(self) -> int:
        return self._local_task_count

    @property
    def remote_task_count(self) -> int:
        return self._remote_task_count


# Global pool singleton
_remote_pool: Optional[RemoteNodePool] = None


def get_remote_pool() -> RemoteNodePool:
    global _remote_pool
    if _remote_pool is None:
        _remote_pool = RemoteNodePool()
    return _remote_pool
