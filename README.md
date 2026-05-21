# SimplePod Surgical Strike Swarm v2.6

> Distributed, highly resilient Agentic Swarm Architecture bridging Shadow PC, local edge hosts, stateless GPU nodes, and hybrid LLM infrastructures.

---

## Architecture Overview

```text
                                ┌──────────────────────────────────────┐
                                │         PUBLIC INTERNET              │
                                │   (API Clients, Webhooks, SMS)       │
                                └──────────────┬───────────────────────┘
                                               │
                                               ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              FASTAPI GATEWAY (Shadow PC)                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                  │
│  │  Auth / Rate    │  │  Request Router │  │  Observability  │                  │
│  │  Limit (GFCI)   │  │  (Main Breaker) │  │  (Panel Meter)  │                  │
│  └────────┬────────┘  └────────┬────────┘  └─────────────────┘                  │
│           │                    │                                                 │
│           └────────────────────┘                                                 │
│                          │                                                       │
│           ┌──────────────┴──────────────┐                                       │
│           ▼                             ▼                                       │
│  ┌─────────────────┐          ┌─────────────────┐                               │
│  │  WebSocket Bus  │          │  Socket.IO Bus  │                               │
│  │  (EMT Conduit)  │          │  (PVC Conduit)  │                               │
│  └────────┬────────┘          └────────┬────────┘                               │
└───────────┼────────────────────────────┼──────────────────────────────────────────┘
            │                            │
            ▼                            ▼
┌────────────────────────┐    ┌────────────────────────────────────────────────────┐
│  LOCAL MSI HOST        │    │  HYBRID LLM POOL                                   │
│  (GTX 1650 Edge)       │    │  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  │
│  ┌──────────────────┐  │    │  │ OpenAI API  │  │ Local API   │  │  Ollama   │  │
│  │  Inference Agent │  │    │  │ (Utility)   │  │ (Generator) │  │ (Backup)  │  │
│  │  (20A Circuit)   │  │    │  └─────────────┘  └─────────────┘  └───────────┘  │
│  └──────────────────┘  │    └────────────────────────────────────────────────────┘
│  Low Latency Fallback  │
└────────────────────────┘
            │
            │  Tailscale / WireGuard Mesh
            │  (The conduit run between buildings)
            ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         STATELESS RTX 5090 NODES (Poland)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  GPU Pod 1  │  │  GPU Pod 2  │  │  GPU Pod 3  │  │  GPU Pod N  │             │
│  │ (30A 240V)  │  │ (30A 240V)  │  │ (30A 240V)  │  │ (30A 240V)  │             │
│  │  Ephemeral  │  │  Ephemeral  │  │  Ephemeral  │  │  Ephemeral  │             │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘             │
│        │                │                │                │                      │
│        └────────────────┴────────────────┴────────────────┘                      │
│                              Auto-Scaler                                         │
│                    (Demand Factor Controller)                                    │
└──────────────────────────────────────────────────────────────────────────────────┘
            │
            ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         PHILIPPINES DEPLOYMENT TARGET                            │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  Reflex UI — Paper Space Layout                                          │   │
│  │  (What the operator sees: viewports, scaled, annotated, ready for sign)  │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Clone & Enter

```bash
git clone https://github.com/simplepod/swarm.git
cd simplepod_swarm
```

### 2. Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate    # Windows
```

### 3. Install Dependencies

```bash
pip install -e ".[dev]"
```

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env with your Tailscale auth key, Twilio creds, and node topology.
```

### 5. Run the Gateway

```bash
uvicorn simplepod.api.gateway:app --reload --host 0.0.0.0 --port 8000
```

### 6. Run the Reflex UI (in another terminal)

```bash
reflex run
```

---

## Module Index

| Module | Path | Purpose |
|--------|------|---------|
| **Gateway** | `src/simplepod/api/gateway.py` | FastAPI entry point — the "front panel" where all requests land. |
| **Router** | `src/simplepod/core/router.py` | Load balancer and inference router — the "main breaker." |
| **Circuit Breaker** | `src/simplepod/core/breaker.py` | Failure isolation logic — like a GFCI that trips on fault. |
| **Node Pool** | `src/simplepod/core/node_pool.py` | Registry of active GPU nodes — the "panel schedule." |
| **Inference Agent** | `src/simplepod/agents/inference.py` | Handles LLM requests — a "20A circuit" dedicated to one load. |
| **Provisioning Agent** | `src/simplepod/agents/provision.py` | Spins up/down RTX 5090 nodes — the "demand factor controller." |
| **WebSocket Bus** | `src/simplepod/transport/websocket.py` | Real-time node communication — "EMT conduit between panels." |
| **Socket.IO Bus** | `src/simplepod/transport/socketio.py` | Fallback real-time transport — "PVC conduit for wet locations." |
| **Twilio Bridge** | `src/simplepod/transport/twilio.py` | SMS/voice command interface — "the intercom system." |
| **Reflex UI** | `src/simplepod/ui/app.py` | Operator dashboard — "paper space layout with viewports." |
| **Tailscale Mesh** | `src/simplepod/infra/tailscale.py` | VPN mesh management — "the underground conduit run." |
| **Cloud Init** | `src/simplepod/infra/cloud_init.py` | Node bootstrap scripts — "the service entrance wiring diagram." |

---

## Development Workflow

```bash
# Format & lint (like cleaning your drawing before the client sees it)
ruff check src tests
ruff format src tests

# Type check (like verifying dimensions before plot)
mypy src

# Run tests (like doing a load calculation before energizing the panel)
pytest

# Run with coverage (like verifying every outlet is grounded)
pytest --cov=src/simplepod --cov-report=html
```

---

## Backup Protocol

> Before modifying ANY file, create a timestamped backup in `E:/ark_backups` (preferred) or `./ark_backups/` (fallback).

Format: `YYYY-MM-DD_HHMM_PST_<filename>`

See [`AGENTS.md`](./AGENTS.md) §4 for the full protocol.

---

## License

MIT © SimplePod Swarm Maintainers
