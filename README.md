# OrbitScribe Swarm Backend

FastAPI-based agent swarm orchestration service for the OrbitScribe ecosystem.

## Features

- **Ask Mode**: Direct chat with LLM (local or cloud)
- **Plan Mode**: Architecture and implementation planning
- **Agent Mode**: Single specialized agent execution
- **Swarm Mode**: Multi-agent parallel delegation with synthesis

## API Modes

| Mode | Behavior |
|------|----------|
| `local_only` | Only Ollama / LM Studio |
| `cloud_only` | Only Gemini / Copilot |
| `hybrid` | Auto-select based on task complexity |

## Quick Start

```bash
pip install -r requirements.txt
python main.py
```

The server starts on `http://127.0.0.1:58081`.

## Endpoints

- `GET /api/health` — Health check
- `POST /api/chat` — Chat (non-streaming)
- `POST /api/chat/stream` — Chat (SSE streaming)
- `POST /api/swarm` — Multi-agent swarm (SSE streaming)
- `POST /api/plan` — Implementation planning
- `POST /api/agent` — Single agent execution
- `GET /api/agents` — List available agents

## Environment Variables

Copy `.env.example` to `.env` and configure:

- `SWARM_API_MODE` — API lockout mode
- `SWARM_PORT` — Server port
- `GEMINI_API_KEY` — For cloud API access
