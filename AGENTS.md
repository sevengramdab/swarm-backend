# SimplePod Surgical Strike Swarm — Agent Instruction File

## 1. Project Overview & Architecture Goals

**SimplePod Surgical Strike Swarm (v2.6)** is a distributed, highly resilient Agentic Swarm Architecture designed to orchestrate heterogeneous compute nodes across multiple geographic and network boundaries. The system bridges:

- **Shadow PC Cloud Workstation** — Primary command & control node, persistent state keeper.
- **Local MSI Host (GTX 1650)** — Edge inference node, low-latency local fallback.
- **Stateless RTX 5090 Nodes (Poland)** — High-throughput GPU workers, ephemeral, auto-scaled.
- **Hybrid Cloud/Local API LLM Infrastructure** — Model serving via external APIs and self-hosted endpoints.
- **Philippines Deployment Target** — Production environment with local regulatory and latency constraints.

### Core Architecture Goals
1. **Surgical Precision** — Each agent performs one task, does it well, and exits cleanly.
2. **Resilience Over Convenience** — Every node is disposable; state lives in message buses and object storage, not on disk.
3. **Zero-Trust Networking** — All inter-node communication is encrypted, authenticated, and rate-limited.
4. **Load-Aware Routing** — Inference requests route to the node with the best latency/cost/availability trade-off, like balancing circuits across a main panel.
5. **Ephemeral Workers** — RTX 5090 nodes spin up on demand, process a batch, and shut down to save cost.

---

## 2. Directory Structure

```
simplepod_swarm/
├── AGENTS.md              # You are here — the blueprint every agent reads before touching code.
├── README.md              # Human-facing quick start and module index.
├── pyproject.toml         # Python packaging, dependencies, and tool configs.
├── .gitignore             # What stays out of version control.
├── src/
│   └── simplepod/
│       ├── __init__.py
│       ├── api/           # FastAPI routers — the "front panel" where external requests land.
│       ├── core/          # Routing engine, circuit breakers, load balancers — the "main breaker."
│       ├── models/        # Pydantic schemas — the "title block" defining every data shape.
│       ├── agents/        # Individual swarm agents — "blocks" that can be inserted into any drawing.
│       ├── transport/     # WebSocket, Socket.IO, HTTP/2 bridges — the "wire runs" between panels.
│       ├── infra/         # Tailscale, cloud-init, node provisioning — the "service entrance."
│       ├── ui/            # Reflex frontend — the "paper space" viewport operators look at.
│       └── utils/         # Shared helpers, backoff logic, timestamping — the "layer 0" utilities.
├── tests/
│   ├── unit/              # Component tests — testing one "outlet" at a time.
│   ├── integration/       # End-to-end circuit tests — the full "load calculation."
│   └── fixtures/          # Mock data, fake nodes, sample payloads — "blocks" reused across drawings.
├── scripts/
│   ├── provision/         # Cloud-init, Terraform, Ansible playbooks — "installation diagrams."
│   └── deploy/            # Dockerfiles, compose files, K8s manifests — "panel schedules."
├── docs/
│   ├── architecture/      # Decision records, topology maps, latency budgets.
│   └── runbooks/          # Incident response, node recovery, failover procedures.
└── ark_backups/           # Local fallback for timestamped file backups (see §4 Backup Protocol).
```

### Directory Analogies (ELI5)
- **`api/`** → *Front Panel / Operator Interface*: This is where the outside world plugs in. Like the front of an electrical panel where breakers are labeled and accessible.
- **`core/`** → *Main Breaker & Bus Bars*: The distribution logic. Power (requests) come in from the service entrance and the main breaker decides which bus bar (node pool) carries the load.
- **`models/`** → *Title Block & Legend*: Every drawing needs a title block. Every API payload needs a Pydantic model. Consistency starts here.
- **`agents/`** → *Reusable CAD Blocks*: A block is drawn once, then inserted anywhere. An agent is coded once, then scheduled anywhere.
- **`transport/`** → *Conduit & Wire Runs*: You don't just throw wires through walls; you run conduit. WebSocket managers, connection pools, and retry logic are our conduit.
- **`infra/`** → *Service Entrance & Meter Base*: Where utility power meets the building. Node provisioning, VPN meshing, and OS hardening happen here.
- **`ui/`** → *Paper Space Layouts*: Model space is messy and full-scale. Paper space is what the client sees — scaled, annotated, viewport-clipped. The Reflex UI is paper space.

---

## 3. Coding Standards

### 3.1 Async-First Python
- **All I/O-bound functions MUST be `async`**. Think of synchronous I/O like running Romex without conduit — it works until someone touches it.
- Use `asyncio.gather` for parallel fan-out (like wiring multiple circuits from the same panel at once).
- Never block the event loop. CPU-heavy work goes to `loop.run_in_executor` or a separate process pool.

### 3.2 Type Hints
- **Every function signature must be fully typed.** No `Any` unless you document why in an ELI5 comment.
- Use `from __future__ import annotations` for forward references.
- Pydantic v2 models for all external boundaries (API requests, WebSocket payloads, config files).

### 3.3 Imports & Formatting
- Order: `__future__`, stdlib, third-party, local (`isort` compatible).
- Line length: 100 characters (configured in `ruff`).
- Use `ruff` for linting and formatting; `mypy --strict` for type checking.
- Run `pytest` with `pytest-asyncio` mode set to `auto`.

### 3.4 Error Handling
- Prefer `structlog` or standard `logging` with contextual fields.
- Circuit-breaker pattern for external calls: if a node trips, isolate it like a breaker until manual reset or cooldown.
- Always propagate `trace_id` through every layer — like a wire label that follows a conductor end-to-end.

### 3.5 Configuration
- Environment variables for secrets and runtime toggles.
- `pyyaml` for static topology definitions (node pools, region mappings).
- Pydantic `BaseSettings` for runtime config validation.

---

## 4. Backup Protocol (NON-NEGOTIABLE)

> **Before ANY file modification, create a timestamped backup.**

### 4.1 Backup Locations (in order of preference)
1. **`E:/ark_backups`** — External drive archive. The "off-site panel."
2. **`./ark_backups/`** — Local project fallback. The "sub-panel next to the main."

### 4.2 Naming Convention
```
YYYY-MM-DD_HHMM_PST_<original_filename>
```

Examples:
```
2026-05-20_1634_PST_pyproject.toml
2026-05-20_1634_PST_src/simplepod/core/router.py
```

### 4.3 Backup Procedure (ELI5)
Think of this like **saving a copy of your AutoCAD drawing before you explode a block**.
You don't want to lose the original block definition if the explode goes wrong.

```bash
# 1. Determine the destination (E: if available, else local)
ARK_DIR="E:/ark_backups"
[ ! -d "$ARK_DIR" ] && ARK_DIR="./ark_backups"

# 2. Create the timestamped backup
cp "path/to/file" "$ARK_DIR/2026-05-20_1634_PST_file.ext"
```

### 4.4 Agent Compliance Checklist
- [ ] Before editing, check if `E:/ark_backups` exists and is writable.
- [ ] If not, ensure `./ark_backups/` exists (create if missing).
- [ ] Copy the original file with the exact timestamp format.
- [ ] Only after the backup is confirmed on disk, proceed with edits.

---

## 5. ELI5 Comment Style Guide

Every non-trivial functional line or block MUST have an ELI5 comment using analogies from **Engineering Graphics**, **AutoCAD**, or **Electrical/Home Automation**.

### 5.1 Approved Analogy Domains
| Domain | Concepts You Can Reference |
|--------|---------------------------|
| Engineering Graphics | Viewports, model space, paper space, scale factors (1:1, 1:10), orthographic projection, isometric, layers (0, Defpoints), title blocks, dimensions, hatch patterns. |
| AutoCAD | Blocks (insert, explode, redefine), polylines (PLINE), UCS / WCS, Osnaps (ENDpoint, MIDpoint), grips, layout tabs, xref, attributes, dynamic blocks, LISP routines. |
| Electrical / Home Automation | Main breaker, sub-panels, circuit breakers (15A, 20A, 30A), load calculation, wire gauges (14 AWG, 12 AWG, 10 AWG), conduit (EMT, PVC), junction boxes, 3-way switches, GFCI, AFCI, panel schedules, demand factors, diversity factor, smart switches (Z-Wave, Zigbee). |

### 5.2 Comment Format
```python
# ELI5: Think of this like <analogy>.
#       <1-2 sentences explaining why this matters in the analogy>.
<actual code>
```

### 5.3 Examples by Layer

#### Example A: Routing / Load Balancing
```python
# ELI5: Think of this like the Main Breaker in your home electrical panel.
#       It decides which circuit (Local GTX 1650 vs Cloud RTX 5090) gets the load.
async def route_inference(request: InferenceRequest) -> RoutingDecision:
```

#### Example B: WebSocket Connection Pool
```python
# ELI5: Think of this like running EMT conduit between two junction boxes.
#       The conduit protects the wires (messages) and gives you a path to pull new ones.
class WebSocketConduit:
```

#### Example C: Pydantic Model Validation
```python
# ELI5: Think of this like the Title Block on an engineering drawing.
#       If the scale factor or part number is missing, the drawing is rejected at the plotter.
class InferenceRequest(BaseModel):
```

#### Example D: Ephemeral Node Shutdown
```python
# ELI5: Think of this like a 3-way switch controlling a light from two locations.
#       Either the Shadow PC OR the local MSI host can decide to cut power to the RTX node.
async def terminate_node(node_id: str, triggered_by: str) -> None:
```

#### Example E: Retry Logic with Backoff
```python
# ELI5: Think of this like using a 20A breaker for a microwave circuit.
#       You try to draw power; if it trips, you wait a few seconds and try again.
#       If it trips 3 times, you call an electrician (the dead-letter queue).
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def call_llm_api(payload: dict) -> dict:
```

### 5.4 When NOT to Comment
- Obvious type hints (`x: int = 5`)
- Standard library imports
- Blank lines
- Closing braces (but a short `# End of <block>` is okay in deeply nested async contexts)

---

## 6. Testing Standards

- **Unit Tests** (`tests/unit/`): Test one "outlet" at a time. Mock all external dependencies.
- **Integration Tests** (`tests/integration/`): Test the full "circuit" from breaker to load. Use `pytest-asyncio` and real transport where feasible.
- **Coverage Target**: 80% line coverage minimum; 100% on `core/` routing logic.
- **Naming**: `test_<module>_<scenario>.py` — e.g., `test_router_fallback_on_node_timeout.py`.

---

## 7. Security & Operational Notes

- **Secrets**: Never commit API keys. Use `.env` files (ignored by Git) and Pydantic `BaseSettings`.
- **Tailscale**: If available, prefer Tailscale IPs for inter-node mesh. Tag nodes by region and role.
- **Rate Limiting**: Every public endpoint gets a circuit breaker AND a rate limiter. Like GFCI + AFCI — redundant protection.
- **Observability**: Every request carries a `trace_id`. Log it at entry, at every handoff, and at exit.

---

## 8. Version & Changelog Discipline

- This project uses **Semantic Versioning**.
- Every agent that modifies a public API must update `docs/architecture/CHANGELOG.md`.
- Format: `## [2.6.1] - 2026-05-20` with Added / Changed / Deprecated / Removed / Fixed / Security sections.

---

## 9. Quick Reference: Agent Mindset

| Situation | Mindset |
|-----------|---------|
| Adding a new node type | "I'm creating a new CAD block that must insert cleanly into any layout." |
| Fixing a routing bug | "I'm troubleshooting why the main breaker keeps feeding the overloaded bus bar." |
| Writing a retry policy | "I'm sizing the wire gauge and breaker amperage so the circuit doesn't overheat." |
| Reviewing a PR | "I'm checking the drawing for missing dimensions and wrong scale factors before it goes to the client." |
| Deploying to Philippines | "I'm verifying the panel schedule matches the local utility's demand factor and voltage standard." |

---

**End of AGENTS.md** — Read this file before every session. Update it when the architecture changes.
