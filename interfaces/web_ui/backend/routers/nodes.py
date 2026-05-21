#!/usr/bin/env python3
"""
routers/nodes.py
================
Node management endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_discovery_daemon, get_endpoint_catalog
from ..models import NodeHealthResponse

router = APIRouter(prefix="/nodes", tags=["nodes"])


def _get_url(ep):
    return ep.get('url') if isinstance(ep, dict) else getattr(ep, 'url', '')


def _get_status(ep):
    val = ep.get('status') if isinstance(ep, dict) else getattr(ep, 'status', 'unknown')
    return val.value if hasattr(val, 'value') else str(val)


def _get_provider(ep):
    val = ep.get('provider') if isinstance(ep, dict) else getattr(ep, 'provider', 'unknown')
    return val.value if hasattr(val, 'value') else str(val)


def _get_models(ep):
    models = ep.get('models') if isinstance(ep, dict) else getattr(ep, 'models', [])
    return [m.get('name') if isinstance(m, dict) else getattr(m, 'name', str(m)) for m in (models or [])]


def _endpoint_to_node(ep):
    url = _get_url(ep)
    last_seen = ep.get('last_seen') if isinstance(ep, dict) else getattr(ep, 'last_seen', 0)
    if hasattr(last_seen, 'timestamp'):
        last_seen = last_seen.timestamp()
    return {
        "node_id": url.replace("http://", "").replace("https://", "").rstrip("/"),
        "status": _get_status(ep),
        "gpu_utilization": ep.get('gpu_utilization') if isinstance(ep, dict) else getattr(ep, 'gpu_utilization', None),
        "vram_used_mb": None,
        "vram_total_mb": None,
        "latency_ms": (ep.get('latency_ms') if isinstance(ep, dict) else getattr(ep, 'latency_ms', 0)) or 0,
        "last_seen": last_seen or 0,
        "provider": _get_provider(ep),
        "models": _get_models(ep),
    }


@router.get("/")
async def list_nodes(catalog=Depends(get_endpoint_catalog)) -> list:
    """List every electrical room in the building."""
    if catalog is not None and hasattr(catalog, 'list_all'):
        endpoints = await catalog.list_all()
        if endpoints:
            return [_endpoint_to_node(ep) for ep in endpoints]
    # Fallback
    return [{
        "node_id": "localhost:11434",
        "status": "healthy",
        "latency_ms": 0,
        "last_seen": __import__('time').time(),
        "provider": "ollama",
        "models": [],
    }]


@router.get("/{node_id}/health")
async def node_health(node_id: str, catalog=Depends(get_endpoint_catalog)) -> NodeHealthResponse:
    """Open one electrical room and read the panel meters."""
    if catalog is not None and hasattr(catalog, 'list_all'):
        endpoints = await catalog.list_all()
        for ep in endpoints:
            ep_id = _get_url(ep).replace("http://", "").replace("https://", "").rstrip("/")
            if ep_id == node_id:
                last_seen = ep.get('last_seen') if isinstance(ep, dict) else getattr(ep, 'last_seen', 0)
                if hasattr(last_seen, 'timestamp'):
                    last_seen = last_seen.timestamp()
                return NodeHealthResponse(
                    node_id=node_id,
                    status=_get_status(ep),
                    latency_ms=(ep.get('latency_ms') if isinstance(ep, dict) else getattr(ep, 'latency_ms', 0)) or 0,
                    last_seen=last_seen or 0,
                )
    raise HTTPException(status_code=404, detail="Node not found")


@router.post("/{node_id}/ping")
async def ping_node(node_id: str, daemon=Depends(get_discovery_daemon)) -> dict:
    """Knock on the door and see if anyone answers."""
    if daemon is not None and hasattr(daemon, "_run_survey_round"):
        await daemon._run_survey_round()
        return {"node_id": node_id, "reachable": True}
    return {"node_id": node_id, "reachable": False, "note": "discovery daemon not available"}


@router.get("/discovery/trigger")
async def trigger_discovery(daemon=Depends(get_discovery_daemon)) -> dict:
    """Send the building engineer on a full inspection round."""
    if daemon is not None and hasattr(daemon, "_run_survey_round"):
        await daemon._run_survey_round()
        return {"status": "scan_triggered"}
    return {"status": "scan_not_available"}
