#!/usr/bin/env python3
"""
main.py
=======
Master entry point for the SimplePod Surgical Strike Swarm.

ELI5: The master electrician's morning routine.
      Walk into the building, flip the main breaker (start swarm),
      check every panel (discovery), turn on the lights (web UI),
      make sure the phone line works (Twilio), and confirm the
      security system is armed (telemetry). If anything breaks,
      know exactly which circuit to check (integration tests).
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path
from typing import Optional

import yaml


# ---------------------------------------------------------------------------
# Configuration loader
# ---------------------------------------------------------------------------
def load_config(path: Optional[Path] = None) -> dict:
    """
    ELI5: Before the electrician touches anything, they read the
          service panel directory sticker (config.yaml) to know
          which circuits serve which rooms.
    """
    cfg_path = path or Path("config.yaml")
    if cfg_path.exists():
        with cfg_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


# ---------------------------------------------------------------------------
# Mode handlers
# ---------------------------------------------------------------------------
async def mode_swarm(cfg: dict) -> None:
    """Start the full swarm: orchestrator, discovery, main breaker, telemetry."""
    print("🔥 Starting SimplePod Swarm in SWARM mode...")
    # Placeholder: wire together real components when imports are resolved.
    print("   [Placeholder] Swarm orchestrator would start here.")
    print("   Press Ctrl+C to shutdown.")
    while True:
        await asyncio.sleep(1)


async def mode_daemon(cfg: dict) -> None:
    """Run discovery + telemetry only."""
    print("📡 Starting SimplePod Daemon...")
    while True:
        await asyncio.sleep(1)


async def mode_web(cfg: dict) -> None:
    """Start FastAPI backend with built-in static dashboard."""
    print("🌐 Starting Web Control Plane...")
    print("   Dashboard: http://localhost:8000")
    print("   API Docs:  http://localhost:8000/docs")
    import uvicorn
    from interfaces.web_ui.backend.main import create_app

    app = create_app()
    host = cfg.get("web", {}).get("host", "0.0.0.0")
    port = cfg.get("web", {}).get("port", 8000)
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def mode_vscode(cfg: dict) -> None:
    """Start backend API server for VS Code extension."""
    print("🧩 Starting VS Code Extension Backend...")
    import uvicorn
    from interfaces.web_ui.backend.main import create_app

    app = create_app()
    host = cfg.get("vscode", {}).get("host", "127.0.0.1")
    port = cfg.get("vscode", {}).get("port", 8001)
    await uvicorn.run(app, host=host, port=port)


async def mode_twilio(cfg: dict) -> None:
    """Start Twilio webhook server."""
    print("📞 Starting Twilio Gateway...")
    while True:
        await asyncio.sleep(1)


async def mode_sitk(cfg: dict) -> None:
    """CLI for packaging and deploying payloads."""
    print("📦 SITK CLI mode — use subcommands: pack, deploy, status")
    # Placeholder for argparse subcommands.
    return


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="SimplePod Surgical Strike Swarm — Master Control",
    )
    parser.add_argument(
        "mode",
        choices=["swarm", "daemon", "web", "vscode", "twilio", "sitk"],
        default="swarm",
        nargs="?",
        help="Operating mode",
    )
    parser.add_argument("--config", "-c", type=Path, default=None, help="Path to config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)

    # Graceful signal handling — like an emergency stop button.
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: sys.exit(0))

    mode_map = {
        "swarm": mode_swarm,
        "daemon": mode_daemon,
        "web": mode_web,
        "vscode": mode_vscode,
        "twilio": mode_twilio,
        "sitk": mode_sitk,
    }

    handler = mode_map[args.mode]
    try:
        asyncio.run(handler(cfg))
    except KeyboardInterrupt:
        print("\n🛑 Shutdown complete.")
        sys.exit(0)


if __name__ == "__main__":
    main()
