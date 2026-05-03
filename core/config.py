"""Swarm backend configuration with API lockout modes."""

import os

API_MODE = os.environ.get("SWARM_API_MODE", "hybrid").lower()
HOST = os.environ.get("SWARM_HOST", "127.0.0.1")
PORT = int(os.environ.get("SWARM_PORT", "58081"))

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
LMSTUDIO_URL = os.environ.get("LMSTUDIO_URL", "http://127.0.0.1:1234")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

LOCAL_MODEL = os.environ.get("LOCAL_MODEL", "qwen2.5-coder")
CLOUD_MODEL = os.environ.get("CLOUD_MODEL", "gemini-2.0-flash")

MAX_AGENTS = int(os.environ.get("MAX_AGENTS", "5"))
SWARM_TIMEOUT = int(os.environ.get("SWARM_TIMEOUT", "120"))
