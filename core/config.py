"""Swarm backend configuration with API lockout modes."""

import os
from enum import Enum
from pydantic_settings import BaseSettings


class APIMode(str, Enum):
    LOCAL_ONLY = "local_only"      # Ollama / LM Studio only
    CLOUD_ONLY = "cloud_only"      # Gemini / OpenAI / Anthropic only
    HYBRID = "hybrid"              # Use both, local preferred
    AUTO = "auto"                  # Auto-detect what's available


class Settings(BaseSettings):
    # API lockout mode
    api_mode: APIMode = APIMode.AUTO
    
    # Server
    host: str = "127.0.0.1"
    port: int = 58081
    
    # Local LLM endpoints
    ollama_url: str = "http://localhost:11434"
    lm_studio_url: str = "http://localhost:1234"
    
    # Cloud API keys (read from env)
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    
    # Default models
    local_model: str = "llama3.2"       # Ollama default
    cloud_model: str = "gemini-1.5-flash"
    
    # Swarm settings
    max_agents: int = 5
    swarm_timeout: int = 120
    
    class Config:
        env_file = ".env"


settings = Settings()
