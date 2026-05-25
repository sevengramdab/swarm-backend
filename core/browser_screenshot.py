"""
BROWSER SCREENSHOT TOOL
Uses the system's existing Chrome installation to capture web pages.
No extra browser downloads needed — Chrome is the camera.
TIMESTAMP: 2026-05-22_1418_PST
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

# Chrome executable path — auto-detect on Windows
_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Users\joshua dyer\AppData\Local\Google\Chrome\Application\chrome.exe",
]

_EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _find_browser() -> Optional[str]:
    """Find Chrome or Edge on the system."""
    for path in _CHROME_PATHS + _EDGE_PATHS:
        if os.path.exists(path):
            return path
    return None


def screenshot_url(
    url: str,
    output_path: Optional[str] = None,
    width: int = 1920,
    height: int = 1080,
    wait_ms: int = 3000,
    full_page: bool = False,
) -> str:
    """
    Take a screenshot of a URL using Chrome headless.

    Args:
        url: The web page to capture
        output_path: Where to save the PNG. If None, uses a temp file.
        width: Viewport width
        height: Viewport height
        wait_ms: How long to wait for page to settle (ms)
        full_page: If True, captures full scrollable page height

    Returns:
        Path to the saved screenshot PNG
    """
    browser = _find_browser()
    if browser is None:
        raise RuntimeError("No Chrome or Edge browser found on this system")

    if output_path is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(tempfile.gettempdir(), f"screenshot_{timestamp}.png")

    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    cmd = [
        browser,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        f"--window-size={width},{height}",
        f"--screenshot={output_path}",
    ]

    if full_page:
        cmd.append("--hide-scrollbars")

    # Wait for page to settle before screenshot
    cmd.extend([
        f"--virtual-time-budget={wait_ms}",
        "--run-all-compositor-stages-before-draw",
    ])

    cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if not os.path.exists(output_path):
        raise RuntimeError(
            f"Screenshot failed. Browser stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    return output_path


def screenshot_localhost(
    path: str = "/",
    port: int = 8000,
    output_path: Optional[str] = None,
    width: int = 1920,
    height: int = 1080,
) -> str:
    """Convenience wrapper for localhost URLs."""
    url = f"http://127.0.0.1:{port}{path}"
    return screenshot_url(url, output_path=output_path, width=width, height=height)
