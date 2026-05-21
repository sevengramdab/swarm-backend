#!/usr/bin/env python3
"""
routers/settings.py
===================
Settings management endpoints.

ELI5: The breaker directory inside the panel door, but digital.
      You can read every label, erase and rewrite them, or
      restore the factory-default stickers.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from ..settings_store import get_settings, update_settings, reset_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def read_settings() -> Dict[str, Any]:
    """Get every setting currently in effect."""
    return get_settings()


@router.put("")
async def write_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update one or more settings. Missing keys stay untouched."""
    return update_settings(updates)


@router.post("/reset")
async def factory_reset() -> Dict[str, Any]:
    """Wipe all custom settings and restore factory defaults."""
    return reset_settings()


@router.get("/defaults")
async def default_settings() -> Dict[str, Any]:
    """Get the factory-default settings without applying them."""
    from ..settings_store import DEFAULT_SETTINGS
    return DEFAULT_SETTINGS
