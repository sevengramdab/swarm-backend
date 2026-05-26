"""
mesh_remote.py
==============
Mesh-wide remote control forwarding.
Allows controlling ANY node in the swarm from the dashboard.
"""
from __future__ import annotations

import base64
import io
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.simpleswarm.remote_client import get_remote_pool

router = APIRouter(prefix="/mesh/remote", tags=["mesh-remote"])


class ClickRequest(BaseModel):
    x: int = Field(..., ge=0)
    y: int = Field(..., ge=0)
    button: str = Field("left")
    clicks: int = Field(1, ge=1, le=3)


class TypeRequest(BaseModel):
    text: str = Field(...)
    interval: float = Field(0.01, ge=0)


class KeysRequest(BaseModel):
    keys: str = Field(...)


class ShellRequest(BaseModel):
    command: str = Field(...)
    cwd: Optional[str] = Field(None)
    timeout: int = Field(30, ge=1, le=300)


class ScrollRequest(BaseModel):
    clicks: int = Field(...)
    x: Optional[int] = Field(None, ge=0)
    y: Optional[int] = Field(None, ge=0)


class DragRequest(BaseModel):
    x1: int = Field(..., ge=0)
    y1: int = Field(..., ge=0)
    x2: int = Field(..., ge=0)
    y2: int = Field(..., ge=0)
    duration: float = Field(0.5, ge=0, le=5)
    button: str = Field("left")


def _get_client(node_id: str):
    pool = get_remote_pool()
    client = pool.nodes.get(node_id)
    if not client:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found in mesh")
    return client


@router.get("/{node_id}/screenshot")
async def mesh_remote_screenshot(node_id: str):
    """Capture screenshot from a remote node."""
    client = _get_client(node_id)
    result = client._request("GET", "/remote/screenshot", timeout=15)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "Screenshot failed"))
    return result.get("data", {})


@router.post("/{node_id}/click")
async def mesh_remote_click(node_id: str, req: ClickRequest):
    """Click on a remote node's screen."""
    client = _get_client(node_id)
    result = client._request("POST", "/remote/click", req.model_dump(), timeout=10)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "Click failed"))
    return result.get("data", {})


@router.post("/{node_id}/type")
async def mesh_remote_type(node_id: str, req: TypeRequest):
    """Type text on a remote node."""
    client = _get_client(node_id)
    result = client._request("POST", "/remote/type", req.model_dump(), timeout=10)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "Type failed"))
    return result.get("data", {})


@router.post("/{node_id}/keys")
async def mesh_remote_keys(node_id: str, req: KeysRequest):
    """Send key combo to a remote node."""
    client = _get_client(node_id)
    result = client._request("POST", "/remote/keys", req.model_dump(), timeout=10)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "Keys failed"))
    return result.get("data", {})


@router.post("/{node_id}/shell")
async def mesh_remote_shell(node_id: str, req: ShellRequest):
    """Execute shell command on a remote node."""
    client = _get_client(node_id)
    result = client._request("POST", "/remote/shell", req.model_dump(), timeout=req.timeout + 5)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "Shell failed"))
    return result.get("data", {})


@router.post("/{node_id}/scroll")
async def mesh_remote_scroll(node_id: str, req: ScrollRequest):
    """Scroll on a remote node."""
    client = _get_client(node_id)
    result = client._request("POST", "/remote/scroll", req.model_dump(), timeout=10)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "Scroll failed"))
    return result.get("data", {})


@router.post("/{node_id}/drag")
async def mesh_remote_drag(node_id: str, req: DragRequest):
    """Drag on a remote node."""
    client = _get_client(node_id)
    result = client._request("POST", "/remote/drag", req.model_dump(), timeout=10)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "Drag failed"))
    return result.get("data", {})
