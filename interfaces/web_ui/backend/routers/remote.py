"""
remote.py
=========
Remote PC control endpoints for the VS Code extension.
ELI5: A wireless remote that can type, click, and run commands
      on the PC where the backend is running.
"""
from __future__ import annotations

import base64
import io
import subprocess
import traceback
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/remote", tags=["remote"])

# Try to import pyautogui; if unavailable, mouse/keyboard endpoints return 503.
try:
    import pyautogui
    _PYAUTOGUI_OK = True
except Exception:
    pyautogui = None  # type: ignore
    _PYAUTOGUI_OK = False


class TypeRequest(BaseModel):
    text: str = Field(..., description="Text to type on the remote PC")
    interval: float = Field(0.01, ge=0, description="Seconds between keystrokes")


class ClickRequest(BaseModel):
    x: int = Field(..., ge=0, description="Screen X coordinate")
    y: int = Field(..., ge=0, description="Screen Y coordinate")
    button: str = Field("left", description="Mouse button: left, right, middle")
    clicks: int = Field(1, ge=1, le=3, description="Number of clicks")


class KeysRequest(BaseModel):
    keys: str = Field(..., description="Key combination, e.g. 'enter', 'ctrl+c', 'alt+tab'")


class ShellRequest(BaseModel):
    command: str = Field(..., description="Shell command to execute")
    cwd: Optional[str] = Field(None, description="Working directory")
    timeout: int = Field(30, ge=1, le=300, description="Seconds to wait for completion")


class ScrollRequest(BaseModel):
    clicks: int = Field(..., description="Scroll amount: positive = up, negative = down")
    x: Optional[int] = Field(None, ge=0, description="Move mouse to X first")
    y: Optional[int] = Field(None, ge=0, description="Move mouse to Y first")


class DragRequest(BaseModel):
    x1: int = Field(..., ge=0, description="Start X coordinate")
    y1: int = Field(..., ge=0, description="Start Y coordinate")
    x2: int = Field(..., ge=0, description="End X coordinate")
    y2: int = Field(..., ge=0, description="End Y coordinate")
    duration: float = Field(0.5, ge=0, le=5, description="Drag duration in seconds")
    button: str = Field("left", description="Mouse button: left, right, middle")


class RemoteResponse(BaseModel):
    success: bool
    message: str


class ScreenshotResponse(BaseModel):
    success: bool
    image_base64: str
    width: int
    height: int


def _check_pyautogui():
    if not _PYAUTOGUI_OK:
        raise HTTPException(
            status_code=503,
            detail="Remote control unavailable: pyautogui not installed or failed to load"
        )


@router.post("/type", response_model=RemoteResponse)
async def remote_type(req: TypeRequest):
    """Type text as if from a keyboard."""
    _check_pyautogui()
    try:
        pyautogui.typewrite(req.text, interval=req.interval)
        return RemoteResponse(success=True, message=f"Typed {len(req.text)} characters")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Type failed: {e}")


@router.post("/click", response_model=RemoteResponse)
async def remote_click(req: ClickRequest):
    """Click the mouse at screen coordinates."""
    _check_pyautogui()
    try:
        pyautogui.click(req.x, req.y, clicks=req.clicks, button=req.button)
        return RemoteResponse(success=True, message=f"Clicked ({req.x}, {req.y}) x{req.clicks}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Click failed: {e}")


@router.post("/keys", response_model=RemoteResponse)
async def remote_keys(req: KeysRequest):
    """Send special key combinations (e.g. 'enter', 'ctrl+c', 'alt+tab')."""
    _check_pyautogui()
    try:
        parts = [p.strip() for p in req.keys.split('+')]
        if len(parts) == 1:
            pyautogui.press(parts[0])
        else:
            pyautogui.hotkey(*parts)
        return RemoteResponse(success=True, message=f"Sent keys: {req.keys}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Keys failed: {e}")


@router.post("/shell", response_model=RemoteResponse)
async def remote_shell(req: ShellRequest):
    """Execute a shell command and return stdout/stderr."""
    try:
        result = subprocess.run(
            req.command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=req.cwd,
            timeout=req.timeout,
        )
        output = result.stdout.strip()
        if result.stderr:
            output += "\n[stderr] " + result.stderr.strip()
        msg = f"Exit {result.returncode} | {output[:200]}"
        return RemoteResponse(
            success=result.returncode == 0,
            message=msg,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail=f"Command timed out after {req.timeout}s")
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Shell failed: {e}")


@router.post("/scroll", response_model=RemoteResponse)
async def remote_scroll(req: ScrollRequest):
    """Scroll the mouse wheel."""
    _check_pyautogui()
    try:
        if req.x is not None and req.y is not None:
            pyautogui.moveTo(req.x, req.y)
        pyautogui.scroll(req.clicks)
        return RemoteResponse(success=True, message=f"Scrolled {req.clicks} clicks")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scroll failed: {e}")


@router.post("/drag", response_model=RemoteResponse)
async def remote_drag(req: DragRequest):
    """Drag the mouse from start to end coordinates."""
    _check_pyautogui()
    try:
        pyautogui.moveTo(req.x1, req.y1)
        pyautogui.dragTo(req.x2, req.y2, duration=req.duration, button=req.button)
        return RemoteResponse(
            success=True,
            message=f"Dragged from ({req.x1}, {req.y1}) to ({req.x2}, {req.y2})"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Drag failed: {e}")


@router.get("/screenshot", response_model=ScreenshotResponse)
async def remote_screenshot():
    """Capture a screenshot and return it as base64 PNG."""
    _check_pyautogui()
    try:
        img = pyautogui.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return ScreenshotResponse(
            success=True,
            image_base64=b64,
            width=img.width,
            height=img.height,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Screenshot failed: {e}")
