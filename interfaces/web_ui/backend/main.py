#!/usr/bin/env python3
"""
main.py
=======
FastAPI application entry point.

ELI5: The main electrical panel in the basement.
      Every circuit breaker (API router) controls a different room:
      /swarm controls the kitchen (orchestrator),
      /nodes controls the workshop (mesh nodes),
      /routing is the Main Breaker itself.
      The panel has a glass door (OpenAPI docs) so electricians
      can read the labels without opening it.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import threading
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .dependencies import init_dependencies
from .routers import nodes, remote, routing, settings as settings_router, sitk, swarm, telemetry, orbstudio, screenshot, hardware, simpleswarm, swarm_coder, mesh, projects, mesh_remote, billing, notifications, stripe_integration, code_quality
from .settings_store import get_settings as _get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    ELI5: The building's morning startup routine.
          Turn on the main breaker, start the HVAC, arm the alarms.
          At night, shut everything down in reverse order.
    """
    # Startup — wire all circuits before the first tenant arrives.
    # We use only the routing module (which has clean imports) for live data.
    from .settings_store import get_setting, get_settings
    settings = get_settings()

    from routing.main_breaker import MainBreaker
    from routing.tier_manager import TierManager, TierConfig, HealthStatus
    from routing.load_balancer import LoadBalancer

    tier_manager = TierManager()
    for t in settings.get('tiers', []):
        await tier_manager.register_tier(
            TierConfig(
                name=t['name'],
                display_name=t.get('display_name', t['name']),
                nodes=t.get('nodes', []),
                models=t.get('models', []),
                health_status=HealthStatus(t.get('health_status', 'healthy'))
            )
        )
    if not settings.get('tiers'):
        await tier_manager.register_tier(
            TierConfig(name="local", display_name="Local MSI GTX 1650", nodes=["local-msi"], models=["llama3.2"], health_status=HealthStatus.HEALTHY)
        )
        await tier_manager.register_tier(
            TierConfig(name="shadow", display_name="Shadow PC", nodes=["shadow-pc"], models=["lmstudio/mistral"], health_status=HealthStatus.HEALTHY)
        )
        await tier_manager.register_tier(
            TierConfig(name="cloud_rtx5090", display_name="Poland RTX 5090", nodes=["poland-01"], models=["gpt-4"], health_status=HealthStatus.HEALTHY)
        )

    # Auto-register nodes from config.yaml into the RemoteNodePool for SwarmCoder routing.
    try:
        from core.simpleswarm.remote_client import get_remote_pool
        import yaml
        import socket
        config_path = Path(__file__).parent.parent.parent.parent / "config.yaml"
        if config_path.exists():
            with open(config_path, "r") as f:
                cfg = yaml.safe_load(f)
            nodes_cfg = cfg.get("nodes", {})
            pool = get_remote_pool()
            # Detect which node WE are by hostname or env override
            my_hostname = socket.gethostname().lower()
            my_node_id = os.environ.get("SIMPLEPOD_NODE_ID", "").lower()
            for node_id, node_data in nodes_cfg.items():
                if node_data.get("status") != "active":
                    continue
                node_hostname = node_data.get("hostname", "").lower()
                # Skip ourselves (match by hostname or explicit NODE_ID)
                if my_node_id and node_id.lower() == my_node_id:
                    print(f"[mesh] Skipping self-registration: {node_id}")
                    continue
                if not my_node_id and node_hostname == my_hostname:
                    print(f"[mesh] Detected self as {node_id} ({my_hostname}) — skipping self-registration")
                    continue
                ip = node_data.get("ip", "")
                if not ip or ip.startswith("127.") or ip == "localhost":
                    continue
                if not ip or ip.startswith("127.") or ip == "localhost":
                    continue
                endpoint = f"http://{ip}:8000"
                vram = node_data.get("vram_mb", 0)
                gpu = node_data.get("gpu_type", "unknown")
                name = node_data.get("hostname", node_id)
                client = pool.register(
                    node_id=node_id,
                    base_url=endpoint,
                    name=f"{name} ({gpu}, {vram}MB)",
                    tier="shadow" if "shadow" in node_id else "cloud",
                    vram_mb=vram,
                )
                healthy = client.health_check()
                print(f"[mesh] Auto-registered {node_id} @ {endpoint} — VRAM: {vram}MB — {'healthy' if healthy else 'unreachable'}")
    except Exception as e:
        print(f"[mesh] Auto-registration from config.yaml failed: {e}")

    # Start continuous mesh discovery in a background thread.
    # Nodes announce themselves via UDP multicast and listen for peers.
    def _discovery_loop():
        import threading
        import time
        try:
            from bridge.mesh.node_registry import announce_presence, discover_nodes
            from core.simpleswarm.remote_client import get_remote_pool
            print("[mesh] Starting continuous discovery loop...")
            while True:
                try:
                    announce_presence()
                    peers = discover_nodes(timeout=3.0)
                    pool = get_remote_pool()
                    for peer in peers:
                        nid = peer.get("node_id")
                        if not nid or nid in pool.nodes:
                            continue
                        endpoint = peer.get("endpoint", "")
                        if not endpoint:
                            continue
                        pool.register(
                            node_id=nid,
                            base_url=endpoint,
                            name=peer.get("name", nid),
                            tier=peer.get("tier", "shadow"),
                            vram_mb=peer.get("vram_mb", 0),
                        )
                        print(f"[mesh] Auto-discovered peer: {nid} @ {endpoint}")
                except Exception as e:
                    pass
                time.sleep(15)
        except ImportError:
            print("[mesh] Discovery module not available, skipping auto-discovery")

    threading.Thread(target=_discovery_loop, daemon=True).start()

    main_breaker = MainBreaker(
        tier_manager=tier_manager,
        load_balancer=LoadBalancer(),
        threshold=settings.get('routing_default_threshold', 0.5)
    )

    # Wire the real Mass Agent Swarm orchestrator.
    from swarm.orchestrator_bridge import OrchestratorBridge
    orchestrator = OrchestratorBridge(
        max_agents=settings.get('swarm_max_agents', 10),
        initial_agents=settings.get('swarm_initial_agents', 3),
        task_timeout=settings.get('swarm_task_timeout_seconds', 30.0),
        auto_scale=settings.get('swarm_auto_scale', True),
    )

    # Simple node catalog — probes local Ollama directly.
    # The full discovery daemon has import issues; this lightweight
    # replacement does the same job for the local node.
    import httpx

    class _SimpleCatalog:
        def __init__(self):
            self._endpoints = []

        async def probe(self):
            try:
                ollama_url = f"http://{settings.get('ollama_host','127.0.0.1')}:{settings.get('ollama_port',11434)}"
                async with httpx.AsyncClient() as client:
                    r = await client.get(f"{ollama_url}/api/tags", timeout=5)
                    models = []
                    if r.status_code == 200:
                        data = r.json()
                        models = [m.get('name','') for m in data.get('models',[])]
                    self._endpoints = [{
                        "url": ollama_url,
                        "provider": "ollama",
                        "models": models,
                        "status": "healthy" if r.status_code == 200 else "offline",
                        "latency_ms": 0,
                        "last_seen": __import__('time').time(),
                        "gpu_utilization": None,
                    }]
            except Exception as e:
                print(f"[discovery] Ollama probe failed: {e}")
                self._endpoints = []

        async def list_all(self):
            return self._endpoints

        async def get(self, url):
            for ep in self._endpoints:
                if ep.get('url') == url:
                    return ep
            return None

    catalog = _SimpleCatalog()
    await catalog.probe()

    class _SimpleDiscovery:
        async def _run_survey_round(self):
            await catalog.probe()

    init_dependencies(
        orchestrator=orchestrator,
        main_breaker=main_breaker,
        telemetry=None,
        discovery=_SimpleDiscovery(),
        catalog=catalog,
    )
    yield
    # Shutdown
    try:
        orchestrator.shutdown(wait=False)
    except Exception:
        pass


def create_app() -> FastAPI:
    """Assemble the panel and mount all breakers."""
    cfg = _get_settings()
    app = FastAPI(
        title=cfg.get('app_name', 'SimplePod Swarm Control Plane'),
        description="Distributed Agentic Swarm Architecture API",
        version=cfg.get('app_version', '2.6.0'),
        lifespan=lifespan,
    )

    # CORS — allow the web dashboard and VS Code extension to talk to us.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.get('cors_origins', ["http://localhost:3000", "http://localhost:8000", "*"]),
        allow_credentials=cfg.get('cors_allow_credentials', True),
        allow_methods=cfg.get('cors_allow_methods', ["*"]),
        allow_headers=cfg.get('cors_allow_headers', ["*"]),
    )

    # Mount circuit breakers.
    app.include_router(swarm.router)
    app.include_router(nodes.router)
    app.include_router(routing.router)
    app.include_router(telemetry.router)
    app.include_router(sitk.router)
    app.include_router(settings_router.router)
    app.include_router(remote.router)
    app.include_router(orbstudio.router)
    app.include_router(screenshot.router)
    app.include_router(hardware.router)
    app.include_router(simpleswarm.router)
    app.include_router(swarm_coder.router)
    app.include_router(projects.router)
    app.include_router(mesh.router)
    app.include_router(mesh_remote.router)
    app.include_router(billing.router)
    app.include_router(notifications.router)
    app.include_router(stripe_integration.router)
    app.include_router(code_quality.router)

    # Serve the static dashboard (replaces broken Streamlit).
    static_dir = Path(__file__).parent.parent / "static"
    react_dir = static_dir / "react"
    
    # Serve React app static assets
    if react_dir.exists():
        app.mount("/static", StaticFiles(directory=str(react_dir)), name="static")
    elif static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/health")
    async def health() -> dict:
        """The green status LED on the panel door."""
        return {"status": "healthy", "service": "simplepod-swarm-api"}

    @app.get("/", include_in_schema=False)
    async def root():
        """Serve the React dashboard at root path."""
        from fastapi.responses import FileResponse
        react_index = react_dir / "index.html"
        if react_index.exists():
            return FileResponse(str(react_index))
        old_index = static_dir / "index.html"
        if old_index.exists():
            return FileResponse(str(old_index))
        return {"status": "ok", "message": "SimplePod Swarm API — visit /docs for documentation"}

    @app.get("/{path:path}", include_in_schema=False)
    async def spa_catchall(path: str):
        """Serve React SPA for all non-API routes."""
        from fastapi.responses import FileResponse
        if path.startswith(("docs", "openapi.json", "redoc")):
            return None
        react_index = react_dir / "index.html"
        if react_index.exists():
            return FileResponse(str(react_index))
        return None

    return app


# Global app instance for `uvicorn main:app`.
app = create_app()
