"""
mesh.py
=======
Node registration and mesh topology for distributed SimplePod.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.simpleswarm.remote_client import get_remote_pool, RemoteNodeClient

router = APIRouter(prefix="/mesh", tags=["mesh"])


class RegisterNodeRequest(BaseModel):
    node_id: str
    name: str = ""
    endpoint: str  # e.g. "http://192.168.1.50:8000"
    tier: str = "shadow"
    models: List[str] = []
    vram_mb: int = 0


class NodeInfo(BaseModel):
    node_id: str
    name: str
    endpoint: str
    tier: str
    models: List[str]
    vram_mb: int
    status: str
    latency_ms: float
    last_seen: float


@router.get("/topology")
async def mesh_topology():
    """Return local node info + all registered remote nodes."""
    pool = get_remote_pool()
    # Run health checks in the background so stale nodes are marked offline
    for client in pool.nodes.values():
        client.health_check()

    # Probe local Ollama for models
    local_models = []
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            r = await client.get("http://localhost:11434/api/tags", timeout=5)
            if r.status_code == 200:
                local_models = [m.get('name', '') for m in r.json().get('models', [])]
    except Exception:
        pass

    local = {
        "node_id": "local",
        "name": "Local Node",
        "endpoint": "http://localhost:8000",
        "tier": "local",
        "models": local_models,
        "vram_mb": 4096,  # Local MSI GTX 1650
        "routing_mode": "auto",
        "local_task_count": pool.local_task_count,
        "remote_task_count": pool.remote_task_count,
    }

    nodes = [client.to_dict() for client in pool.nodes.values()]
    return {"local": local, "nodes": nodes}


@router.post("/nodes/register")
async def register_node(req: RegisterNodeRequest):
    """Register a remote SimplePod node."""
    pool = get_remote_pool()
    client = pool.register(req.node_id, req.endpoint, name=req.name or req.node_id, tier=req.tier, vram_mb=req.vram_mb)
    healthy = client.health_check()
    return {
        "success": True,
        "node_id": req.node_id,
        "healthy": healthy,
        "message": f"Node {req.node_id} registered {'(healthy)' if healthy else '(unreachable)'}"
    }


@router.delete("/nodes/{node_id}")
async def unregister_node(node_id: str):
    """Remove a remote node."""
    pool = get_remote_pool()
    if pool.deregister(node_id):
        return {"success": True, "message": f"Node {node_id} removed"}
    raise HTTPException(status_code=404, detail=f"Node {node_id} not found")


@router.post("/nodes/discover")
async def discover_nodes():
    """Trigger node discovery (placeholder — multicast + Tailscale)."""
    # In a full implementation, this would call bridge.mesh.node_registry.discover_nodes()
    # For now, we just return the current pool after refreshing health.
    pool = get_remote_pool()
    discovered = []
    for client in list(pool.nodes.values()):
        if client.health_check():
            discovered.append(client.node_id)
    return {"success": True, "discovered": discovered, "message": f"{len(discovered)} nodes healthy"}


@router.get("/nodes")
async def list_nodes():
    """List all registered mesh nodes with health status."""
    pool = get_remote_pool()
    return {"nodes": pool.health_summary()}


@router.post("/{node_id}/health")
async def check_node_health(node_id: str):
    """Manually trigger a health check on a remote node."""
    pool = get_remote_pool()
    client = pool.nodes.get(node_id)
    if not client:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    healthy = client.health_check()
    return {"node_id": node_id, "healthy": healthy, "url": client.base_url}


@router.get("/{node_id}/models")
async def node_models(node_id: str):
    """Ask a remote node what models it has available."""
    pool = get_remote_pool()
    client = pool.nodes.get(node_id)
    if not client:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    result = client.list_models()
    return result.get("data", {"error": result.get("error", "unknown")})


@router.get("/{node_id}/metrics")
async def node_metrics(node_id: str):
    """Get compute metrics from a remote node."""
    pool = get_remote_pool()
    client = pool.nodes.get(node_id)
    if not client:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    result = client.get_metrics()
    return result.get("data", {"error": result.get("error", "unknown")})
