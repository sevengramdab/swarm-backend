"""
computer_controller.py
======================
High-level wrapper around pyautogui for MassAgent workers.
Every method is a synchronous callable that can be passed directly
to MassAgentOrchestrator as a task payload.

ELI5: A robot hand that can click, type, take pictures, and run commands.
"""
from __future__ import annotations

import os
import io
import sys
import time
import base64
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple, List
from PIL import Image

# ---------------------------------------------------------------------------
# pyautogui safety & setup
# ---------------------------------------------------------------------------
try:
    import pyautogui
    pyautogui.FAILSAFE = True          # move mouse to corner = emergency stop
    pyautogui.PAUSE = 0.05             # small delay between actions
    _PYAUTOGUI_OK = True
except Exception:
    pyautogui = None  # type: ignore
    _PYAUTOGUI_OK = False


class ComputerController:
    """
    Controls the local computer via pyautogui + subprocess.
    All methods are safe, logged, and return structured results.
    """

    def __init__(self, screenshot_dir: Optional[str] = None):
        self.screen_w, self.screen_h = self._get_screen_size()
        self.screenshot_dir = Path(screenshot_dir or tempfile.gettempdir()) / "simpleswarm_screenshots"
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self._action_log: List[dict] = []

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _get_screen_size(self) -> Tuple[int, int]:
        if _PYAUTOGUI_OK:
            return pyautogui.size()
        return (1920, 1080)

    def _log(self, action: str, detail: str = "", success: bool = True):
        entry = {
            "timestamp": time.time(),
            "action": action,
            "detail": detail,
            "success": success,
        }
        self._action_log.append(entry)

    def _rel_to_abs(self, x_pct: float, y_pct: float) -> Tuple[int, int]:
        """Convert percentage coordinates (0.0-1.0) to absolute pixels."""
        return int(x_pct * self.screen_w), int(y_pct * self.screen_h)

    # -----------------------------------------------------------------------
    # Mouse
    # -----------------------------------------------------------------------

    def move_to(self, x: int, y: int, duration: float = 0.25) -> dict:
        """Move mouse to absolute screen coordinates."""
        if not _PYAUTOGUI_OK:
            return {"success": False, "error": "pyautogui not available"}
        try:
            pyautogui.moveTo(x, y, duration=duration)
            self._log("move_to", f"({x}, {y})")
            return {"success": True, "x": x, "y": y}
        except Exception as e:
            self._log("move_to", str(e), success=False)
            return {"success": False, "error": str(e)}

    def move_rel(self, x_pct: float, y_pct: float, duration: float = 0.25) -> dict:
        """Move mouse to percentage of screen (0.0-1.0)."""
        x, y = self._rel_to_abs(x_pct, y_pct)
        return self.move_to(x, y, duration)

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> dict:
        """Click at absolute screen coordinates."""
        if not _PYAUTOGUI_OK:
            return {"success": False, "error": "pyautogui not available"}
        try:
            pyautogui.click(x, y, clicks=clicks, button=button)
            self._log("click", f"({x}, {y}) button={button} clicks={clicks}")
            return {"success": True, "x": x, "y": y, "button": button, "clicks": clicks}
        except Exception as e:
            self._log("click", str(e), success=False)
            return {"success": False, "error": str(e)}

    def click_rel(self, x_pct: float, y_pct: float, button: str = "left", clicks: int = 1) -> dict:
        """Click at percentage of screen (0.0-1.0)."""
        x, y = self._rel_to_abs(x_pct, y_pct)
        return self.click(x, y, button, clicks)

    def right_click(self, x: int, y: int) -> dict:
        return self.click(x, y, button="right")

    def double_click(self, x: int, y: int) -> dict:
        return self.click(x, y, clicks=2)

    def scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None) -> dict:
        """Scroll mouse wheel. Positive = up, negative = down."""
        if not _PYAUTOGUI_OK:
            return {"success": False, "error": "pyautogui not available"}
        try:
            if x is not None and y is not None:
                pyautogui.moveTo(x, y)
            pyautogui.scroll(clicks)
            self._log("scroll", f"clicks={clicks} at ({x}, {y})")
            return {"success": True, "clicks": clicks}
        except Exception as e:
            self._log("scroll", str(e), success=False)
            return {"success": False, "error": str(e)}

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.5, button: str = "left") -> dict:
        """Drag from (x1,y1) to (x2,y2)."""
        if not _PYAUTOGUI_OK:
            return {"success": False, "error": "pyautogui not available"}
        try:
            pyautogui.moveTo(x1, y1)
            pyautogui.dragTo(x2, y2, duration=duration, button=button)
            self._log("drag", f"({x1},{y1}) -> ({x2},{y2})")
            return {"success": True, "x1": x1, "y1": y1, "x2": x2, "y2": y2}
        except Exception as e:
            self._log("drag", str(e), success=False)
            return {"success": False, "error": str(e)}

    # -----------------------------------------------------------------------
    # Keyboard
    # -----------------------------------------------------------------------

    def type_text(self, text: str, interval: float = 0.01) -> dict:
        """Type a string as if from a keyboard."""
        if not _PYAUTOGUI_OK:
            return {"success": False, "error": "pyautogui not available"}
        try:
            pyautogui.typewrite(text, interval=interval)
            self._log("type_text", f"len={len(text)}")
            return {"success": True, "chars": len(text)}
        except Exception as e:
            self._log("type_text", str(e), success=False)
            return {"success": False, "error": str(e)}

    def hotkey(self, *keys: str) -> dict:
        """Send a key combination, e.g. hotkey('ctrl', 'c')."""
        if not _PYAUTOGUI_OK:
            return {"success": False, "error": "pyautogui not available"}
        try:
            pyautogui.hotkey(*keys)
            self._log("hotkey", "+".join(keys))
            return {"success": True, "keys": list(keys)}
        except Exception as e:
            self._log("hotkey", str(e), success=False)
            return {"success": False, "error": str(e)}

    def press(self, key: str) -> dict:
        """Press a single key, e.g. press('enter')."""
        if not _PYAUTOGUI_OK:
            return {"success": False, "error": "pyautogui not available"}
        try:
            pyautogui.press(key)
            self._log("press", key)
            return {"success": True, "key": key}
        except Exception as e:
            self._log("press", str(e), success=False)
            return {"success": False, "error": str(e)}

    # -----------------------------------------------------------------------
    # Screenshot
    # -----------------------------------------------------------------------

    def screenshot(self, save: bool = True, filename: Optional[str] = None) -> dict:
        """
        Capture desktop screenshot.
        Returns: {"success", "image", "image_base64", "width", "height", "path"}
        """
        if not _PYAUTOGUI_OK:
            return {"success": False, "error": "pyautogui not available"}
        try:
            img = pyautogui.screenshot()
            w, h = img.size
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

            path = None
            if save:
                fname = filename or f"screenshot_{int(time.time())}.png"
                path = self.screenshot_dir / fname
                img.save(path)

            self._log("screenshot", f"{w}x{h}")
            return {
                "success": True,
                "image": img,
                "image_base64": b64,
                "width": w,
                "height": h,
                "path": str(path) if path else None,
            }
        except Exception as e:
            self._log("screenshot", str(e), success=False)
            return {"success": False, "error": str(e)}

    # -----------------------------------------------------------------------
    # Shell & Process
    # -----------------------------------------------------------------------

    def shell(self, command: str, cwd: Optional[str] = None, timeout: int = 30) -> dict:
        """Execute a shell command."""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout,
            )
            out = result.stdout.strip()
            err = result.stderr.strip()
            self._log("shell", f"cmd='{command[:60]}' exit={result.returncode}")
            return {
                "success": result.returncode == 0,
                "exit_code": result.returncode,
                "stdout": out,
                "stderr": err,
            }
        except subprocess.TimeoutExpired:
            self._log("shell", f"timeout: {command[:60]}", success=False)
            return {"success": False, "error": f"Timeout after {timeout}s"}
        except Exception as e:
            self._log("shell", str(e), success=False)
            return {"success": False, "error": str(e)}

    def kill_process(self, name: str) -> dict:
        """Kill all processes matching a name (Windows)."""
        return self.shell(f'taskkill //IM {name} //F 2>nul')

    # -----------------------------------------------------------------------
    # Browser / Apps
    # -----------------------------------------------------------------------

    def open_browser(self, url: str, browser_path: Optional[str] = None) -> dict:
        """Open a URL in Chrome (or default browser)."""
        chrome = browser_path or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        if os.path.exists(chrome):
            cmd = f'start "" "{chrome}" "{url}"'
        else:
            cmd = f'start "" "{url}"'
        return self.shell(cmd)

    def open_vscode(self, path: str) -> dict:
        """Open a folder in VS Code."""
        return self.shell(f'code "{path}"')

    def open_batch(self, batch_path: str) -> dict:
        """Double-click a batch file (Windows)."""
        return self.shell(f'start "" "{batch_path}"')

    # -----------------------------------------------------------------------
    # Wait / Sleep
    # -----------------------------------------------------------------------

    def sleep(self, seconds: float) -> dict:
        """Sleep for N seconds."""
        time.sleep(seconds)
        self._log("sleep", f"{seconds}s")
        return {"success": True, "seconds": seconds}

    def wait_for_port(self, port: int, timeout: int = 30) -> dict:
        """Poll until a TCP port is listening."""
        import socket
        start = time.time()
        while time.time() - start < timeout:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                s.connect(("localhost", port))
                s.close()
                self._log("wait_for_port", f"port {port} ready")
                return {"success": True, "port": port, "waited": round(time.time() - start, 1)}
            except Exception:
                time.sleep(1)
        return {"success": False, "error": f"Port {port} not ready after {timeout}s"}

    # -----------------------------------------------------------------------
    # HTTP (for API testing within computer control)
    # -----------------------------------------------------------------------

    def http_get(self, url: str, timeout: int = 10) -> dict:
        """Simple HTTP GET using urllib (no external deps)."""
        try:
            import urllib.request
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "SimpleSwarm/1.0")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
                self._log("http_get", f"{url} -> {resp.status}")
                return {"success": True, "status": resp.status, "body": body[:50000]}
        except Exception as e:
            self._log("http_get", f"{url} -> {e}", success=False)
            return {"success": False, "error": str(e)}

    def http_post(self, url: str, json_data: dict, timeout: int = 10) -> dict:
        """Simple HTTP POST with JSON body."""
        try:
            import urllib.request
            import json
            data = json.dumps(json_data).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("User-Agent", "SimpleSwarm/1.0")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
                self._log("http_post", f"{url} -> {resp.status}")
                return {"success": True, "status": resp.status, "body": body[:50000]}
        except Exception as e:
            self._log("http_post", f"{url} -> {e}", success=False)
            return {"success": False, "error": str(e)}

    # -----------------------------------------------------------------------
    # Utility
    # -----------------------------------------------------------------------

    def get_action_log(self) -> List[dict]:
        """Return the full action history."""
        return self._action_log.copy()

    def clear_action_log(self):
        """Clear the action history."""
        self._action_log.clear()

    def get_screen_size(self) -> dict:
        return {"success": True, "width": self.screen_w, "height": self.screen_h}
