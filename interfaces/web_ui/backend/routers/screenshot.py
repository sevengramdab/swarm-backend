"""
SCREENSHOT ROUTER — Browser Camera Tool
Lets the swarm capture and analyze any web page visually.
"""

from __future__ import annotations

import os
from fastapi import APIRouter, Query
from fastapi.responses import FileResponse
from core.browser_screenshot import screenshot_url, _find_browser

router = APIRouter(prefix="/screenshot", tags=["screenshot"])


@router.get("/")
async def screenshot_page(
    url: str = Query(..., description="URL to capture"),
    width: int = Query(1920, ge=320, le=3840),
    height: int = Query(1080, ge=240, le=2160),
    wait: int = Query(3000, ge=0, le=30000),
):
    """
    Point the browser camera at any URL and snap a photo.
    Returns a PNG image of the rendered page.
    """
    if _find_browser() is None:
        return {"error": "No Chrome or Edge browser found on this system"}

    output_path = screenshot_url(url, width=width, height=height, wait_ms=wait)
    return FileResponse(output_path, media_type="image/png", filename="screenshot.png")


@router.get("/localhost")
async def screenshot_localhost(
    path: str = Query("/", description="Path on localhost:8000"),
    width: int = Query(1920, ge=320, le=3840),
    height: int = Query(1080, ge=240, le=2160),
    wait: int = Query(3000, ge=0, le=30000),
):
    """Quick shortcut: screenshot http://localhost:8000/{path}"""
    url = f"http://127.0.0.1:8000{path}"
    output_path = screenshot_url(url, width=width, height=height, wait_ms=wait)
    return FileResponse(output_path, media_type="image/png", filename="screenshot.png")
