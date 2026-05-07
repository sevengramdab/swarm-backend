"""Swarm backend configuration with API lockout modes."""

import os

API_MODE = os.environ.get("SWARM_API_MODE", "hybrid").lower()
HOST = os.environ.get("SWARM_HOST", "127.0.0.1")
PORT = int(os.environ.get("SWARM_PORT", "58081"))

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
LMSTUDIO_URL = os.environ.get("LMSTUDIO_URL", "http://127.0.0.1:1234")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
KIMI_API_KEY = os.environ.get("KIMI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "")

LOCAL_MODEL = os.environ.get("LOCAL_MODEL", "qwen2.5-coder:14b")
CLOUD_MODEL = os.environ.get("CLOUD_MODEL", "gemini-2.0-flash")
ORCHESTRATOR_MODEL = os.environ.get("ORCHESTRATOR_MODEL", CLOUD_MODEL)

MAX_AGENTS = int(os.environ.get("MAX_AGENTS", "5"))
SWARM_TIMEOUT = int(os.environ.get("SWARM_TIMEOUT", "120"))

# LLM temperature: 0 = deterministic, 1 = very creative
TEMPERATURE = float(os.environ.get("SWARM_TEMPERATURE", "0.7"))

# Subagent spawning mode: cloud | local | hybrid
SUBAGENT_MODE = os.environ.get("SUBAGENT_MODE", "hybrid").lower()

# Workspace root for tool execution (set by extension per-session)
WORKSPACE_ROOT = os.environ.get("ORBITSCRIBE_WORKSPACE_ROOT", "")

