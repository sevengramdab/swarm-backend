# SimplePod Surgical Strike Swarm — Module Manifest v2.6

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SIMPLEPOD SURGICAL STRIKE v2.6                       │
│          Hybrid Core Architecture — Philippines Deployment              │
├─────────────────────────────────────────────────────────────────────────┤
│  CONTROL PLANE                                                          │
│  ├── VS Code Extension    (TypeScript)  ← IDE dashboard, agent trees    │
│  ├── Web UI               (Streamlit)   ← Main Breaker slider, charts   │
│  ├── FastAPI Backend      (Python)      ← REST + SSE API gateway        │
│  └── Twilio Gateway       (Python)      ← SMS/MMS for mom               │
├─────────────────────────────────────────────────────────────────────────┤
│  SWARM ORCHESTRATION                                                    │
│  ├── Memory Bus           (Python)      ← Layer Properties Manager      │
│  ├── Context Manager      (Python)      ← Viewport snapshot manager     │
│  ├── Agent Registry       (Python)      ← Construction site logbook     │
│  ├── State Serializer     (Python)      ← ETRANSMIT / ZIP state packs   │
│  ├── Reallocation Ctrl    (Python)      ← Auto load transfer switch     │
│  ├── Bottleneck Detector  (Python)      ← Panel amp-meter monitoring    │
│  ├── Migration Engine     (Python)      ← Moving truck for agent brains │
│  ├── Telemetry Logger     (Python)      ← Security camera DVR           │
│  ├── Telemetry Analyzer   (Python)      ← Foreman reading logbooks      │
│  └── Adaptive Optimizer   (Python)      ← Self-improving site plans     │
├─────────────────────────────────────────────────────────────────────────┤
│  COMPUTE ROUTING ("The Main Breaker")                                   │
│  ├── Main Breaker         (Python)      ← Transfer switch + GFCI trips  │
│  ├── Complexity Scorer    (Python)      ← Load calculation sheet        │
│  ├── Tier Manager         (Python)      ← Power source directory        │
│  └── Load Balancer        (Python)      ← Smart panel load shedding     │
├─────────────────────────────────────────────────────────────────────────┤
│  HARDWARE BRIDGE                                                        │
│  ├── Mesh Configurator    (Python)      ← Tailscale/WireGuard configs   │
│  ├── Node Registry        (Python)      ← Building directory            │
│  ├── Tunnel Manager       (Python)      ← Encrypted conduit between bldg│
│  ├── Discovery Daemon     (Python)      ← Survey team checking plotters │
│  ├── Endpoint Catalog     (Python)      ← Master floor plan of devices  │
│  ├── Health Checker       (Python)      ← Inspection forms for devices  │
│  ├── Cloud Router         (Python)      ← Utility grid auto-transfer    │
│  └── Provider Connectors  (Python)      ← OpenAI, Anthropic, Google     │
├─────────────────────────────────────────────────────────────────────────┤
│  CORE INFRASTRUCTURE                                                    │
│  ├── SITK Packager        (Python)      ← Warehouse boxing station      │
│  ├── SITK Deployer        (Python)      ← UPS truck dispatcher          │
│  ├── SITK Executor        (Python)      ← On-site electrician           │
│  ├── SITK Orchestrator    (Python)      ← Construction project manager  │
│  └── Backup Protocol      (Python)      ← Fireproof photo safe          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Agent Assignment Index

| Agent | Module | Status | Files |
|-------|--------|--------|-------|
| **001** | Project Scaffold | ✅ Complete | `AGENTS.md`, `README.md`, `pyproject.toml`, `.gitignore` |
| **002** | SITK Core | ✅ Complete | `sitk_packager.py`, `sitk_deployer.py`, `sitk_executor.py`, `sitk_orchestrator.py` |
| **003** | Backup Protocol | ✅ Complete | `backup_engine.py`, `safe_file_ops.py`, `backup_cli.py` |
| **004** | Hardware Bridge Mesh | ✅ Complete | `mesh_configurator.py`, `node_registry.py`, `tunnel_manager.py`, `scripts/setup_tailscale.ps1`, `scripts/setup_wireguard.sh` |
| **005** | Local LLM Discovery | ✅ Complete | `discovery_daemon.py`, `endpoint_catalog.py`, `health_checker.py`, `discovery_client.py` |
| **006** | Cloud API Connectors | ✅ Complete | `cloud_router.py`, `cost_tracker.py`, `providers/{base,openai,anthropic,google}.py` |
| **007** | Kimi Memory Bus | ✅ Complete | `memory_bus.py`, `context_manager.py`, `agent_registry.py`, `state_serializer.py` |
| **008** | Reallocation Controller | ✅ Complete | `reallocation_controller.py`, `bottleneck_detector.py`, `execution_graph.py`, `migration_engine.py` |
| **009** | Telemetry & Growth | ✅ Complete | `telemetry_logger.py`, `telemetry_analyzer.py`, `adaptive_optimizer.py`, `telemetry_dashboard_data.py` |
| **010** | Main Breaker Router | ✅ Complete | `main_breaker.py`, `complexity_scorer.py`, `tier_manager.py`, `load_balancer.py` |
| **011** | VS Code Extension | ✅ Complete | `package.json`, `src/extension.ts`, `src/panels/DashboardPanel.ts`, `src/providers/{Agent,Node,Transfer}TreeProvider.ts`, `src/api/client.ts`, `tsconfig.json` |
| **012** | FastAPI Web Backend | ✅ Complete | `main.py`, `models.py`, `dependencies.py`, `routers/{swarm,nodes,routing,telemetry,sitk}.py` |
| **013** | Web Frontend | ✅ Complete | `streamlit_dashboard.py`, `requirements.txt` |
| **014** | Twilio Gateway | ✅ Complete | `webhook_server.py`, `command_parser.py`, `response_builder.py`, `auth_manager.py`, `twilio_client.py`, `templates/status_mms.html` |
| **015** | Integration & Tests | ✅ Complete | `main.py`, `config.yaml`, `scripts/start_swarm.{ps1,sh}`, `tests/{conftest,test_sitk_packager,test_backup_engine,test_discovery_daemon,test_main_breaker,test_integration}.py`, `MANIFEST.md` |

---

## Quick Start

```bash
# 1. Enter the project
cd simplepod_swarm

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Configure
cp config.yaml config.local.yaml
# Edit config.local.yaml with your API keys and node addresses

# 5. Start the swarm (Windows)
.\scripts\start_swarm.ps1

# 5b. Start the swarm (Linux / Cloud nodes)
bash scripts/start_swarm.sh

# 6. Open the web dashboard
streamlit run interfaces/web_ui/frontend/streamlit_dashboard.py

# 7. Open API docs
open http://localhost:8000/docs
```

---

## Backup Protocol Reminder

> **Before ANY file modification**, the system creates a timestamped backup:
> - Target: `E:/ark_backups` or local `./ark_backups/`
> - Format: `YYYY-MM-DD_HHMM_PST`
> - Overwrites in-place (single source of truth)
> - No `.bak` or `.tmp` clutter

---

## ELI5 Style Guide

Every Python module uses analogies from:
- **Engineering Graphics** (title blocks, dimension lines, scale factors, viewports)
- **AutoCAD** (Model Space, Paper Space, Layers, Blocks, UCS, LAYDEL, ETRANSMIT)
- **Electrical / Home Automation** (Main Breaker, circuits, load shedding, GFCI, transfer switches, smart panels)

---

*Generated by the SimplePod Mass Agent Swarm — 15 agents deployed.*
