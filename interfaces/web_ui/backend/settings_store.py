#!/usr/bin/env python3
"""
settings_store.py
=================
Persistent JSON-backed settings store for the SimplePod Swarm control plane.

ELI5: Like the labeled breaker directory inside the panel door.
      Every switch position, threshold, and preference is written down
      so the next electrician knows exactly how the building is configured.
"""

from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

# Default settings — every hardcoded value from the codebase lives here now.
DEFAULT_SETTINGS: Dict[str, Any] = {
    # ─── App ────────────────────────────────────────────────────────────────
    "app_name": "SimplePod Swarm Backend",
    "app_version": "2.6.0",
    "debug": False,
    "log_level": "INFO",

    # ─── API / Server ───────────────────────────────────────────────────────
    "api_host": "0.0.0.0",
    "api_port": 8000,
    "api_base_url": "http://localhost:8000",
    "cors_origins": ["http://localhost:3000", "http://localhost:8000", "*"],
    "cors_allow_credentials": True,
    "cors_allow_methods": ["*"],
    "cors_allow_headers": ["*"],
    "request_timeout_seconds": 30.0,
    "api_retry_count": 3,
    "api_retry_delay_seconds": 1.0,

    # ─── Ollama / LLM ───────────────────────────────────────────────────────
    "ollama_host": "127.0.0.1",
    "ollama_port": 11434,
    "ollama_base_url": "http://localhost:11434",
    "ollama_models_path": "/d/ollama/models",
    "default_model": "llama3.2",
    "default_temperature": 0.7,
    "default_system_prompt": "You are a helpful assistant.",
    "default_max_tokens": 256,
    "default_top_p": 0.9,
    "default_top_k": 40,
    "default_repeat_penalty": 1.1,
    "ollama_keep_alive_minutes": 5,
    "ollama_num_parallel": 1,
    "ollama_context_length": 4096,
    "ollama_gpu_overhead_mb": 0,
    "ollama_flash_attention": False,
    "ollama_vulkan": False,
    "preload_models_on_startup": False,
    "models_to_preload": [],

    # ─── Swarm / Orchestrator ───────────────────────────────────────────────
    "swarm_max_agents": 10,
    "swarm_initial_agents": 3,
    "swarm_task_timeout_seconds": 30.0,
    "swarm_auto_scale": True,
    "swarm_worker_threads": 4,
    "swarm_agent_spawn_delay_seconds": 0.5,
    "swarm_max_pending_tasks": 100,
    "swarm_agent_idle_timeout_seconds": 300,
    "swarm_agent_max_lifetime_seconds": 3600,
    "swarm_enable_gpu_scheduling": True,
    "swarm_gpu_memory_threshold_percent": 85,

    # ─── Routing / Main Breaker ─────────────────────────────────────────────
    "routing_default_threshold": 0.5,
    "routing_default_mode": "auto",
    "routing_complexity_weight_reasoning": 0.25,
    "routing_complexity_weight_tools": 0.20,
    "routing_complexity_weight_tokens": 0.20,
    "routing_complexity_weight_latency": 0.20,
    "routing_complexity_weight_cost": 0.15,
    "routing_token_threshold_low": 128,
    "routing_token_threshold_high": 1024,
    "routing_latency_threshold_ms": 5000,
    "routing_cost_threshold_usd": 0.01,
    "routing_enable_tier_health_check": True,
    "routing_tier_health_check_interval_seconds": 30,
    "routing_fallback_to_local_on_failure": True,
    "routing_max_retries_per_tier": 2,
    "routing_retry_backoff_seconds": 2.0,

    # ─── Tiers ──────────────────────────────────────────────────────────────
    # Only the local Ollama instance. Remote tiers are added dynamically
    # when nodes are discovered via the discovery daemon.
    "tiers": [
        {
            "name": "local",
            "display_name": "Local GTX 1070",
            "nodes": ["local-ollama"],
            "models": ["llama3.2"],
            "health_status": "healthy",
            "priority": 1,
            "cost_per_token": 0.0,
            "avg_latency_ms": 500,
        },
    ],

    # ─── UI / Dashboard ─────────────────────────────────────────────────────
    "ui_poll_interval_ms": 2000,
    "ui_telemetry_log_max_entries": 50,
    "ui_error_banner_auto_hide_ms": 5000,
    "ui_task_poll_interval_ms": 2000,
    "ui_task_poll_max_attempts": 60,
    "ui_theme": "dark",
    "ui_font_size": "medium",
    "ui_enable_sse_stream": True,
    "ui_auto_refresh": True,
    "ui_show_gpu_bars": True,
    "ui_show_agent_stats": True,
    "ui_compact_mode": False,
    "ui_date_format": "24h",
    "ui_language": "en",

    # ─── Telemetry ──────────────────────────────────────────────────────────
    "telemetry_output_dir": "telemetry_logs",
    "telemetry_sse_heartbeat_seconds": 2,
    "telemetry_history_limit": 100,
    "telemetry_enable_disk_logging": True,
    "telemetry_enable_memory_buffer": True,
    "telemetry_memory_buffer_size": 1000,
    "telemetry_log_agent_lifecycle": True,
    "telemetry_log_task_lifecycle": True,
    "telemetry_log_routing_decisions": True,
    "telemetry_log_performance_metrics": True,
    "telemetry_batch_write_interval_seconds": 10,

    # ─── Discovery / Nodes ──────────────────────────────────────────────────
    "discovery_scan_interval_seconds": 60,
    "discovery_ping_timeout_seconds": 5,
    "discovery_max_nodes": 50,
    "discovery_enable_mdns": False,
    "discovery_enable_broadcast": True,
    "discovery_broadcast_port": 8765,
    "discovery_node_timeout_seconds": 120,

    # ─── SITK / Deployment ──────────────────────────────────────────────────
    "sitk_chunk_size_bytes": 1048576,
    "sitk_max_transfer_retries": 3,
    "sitk_transfer_timeout_seconds": 300,
    "sitk_enable_compression": True,
    "sitk_compression_level": 6,
    "sitk_verify_checksum": True,

    # ─── Security ───────────────────────────────────────────────────────────
    "enable_api_key_auth": False,
    "api_key": "",
    "enable_rate_limiting": False,
    "rate_limit_requests_per_minute": 60,
    "enable_cors": True,
    "require_https": False,
    "max_request_body_size_mb": 50,

    # ─── Cache ──────────────────────────────────────────────────────────────
    "enable_response_cache": True,
    "cache_max_entries": 1000,
    "cache_ttl_seconds": 300,
    "cache_similarity_threshold": 0.95,
}

# Thread-safe singleton
_lock = threading.RLock()
_settings: Dict[str, Any] = deepcopy(DEFAULT_SETTINGS)


def _settings_path() -> Path:
    """Path to the persistent JSON settings file."""
    # Store next to the backend folder so it survives reinstalls.
    base = Path(__file__).parent.parent
    return base / "settings.json"


def load_settings() -> Dict[str, Any]:
    """Load settings from disk, merging with defaults for any missing keys."""
    global _settings
    path = _settings_path()
    with _lock:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                # Merge with defaults so new settings keys auto-appear after upgrades.
                merged = deepcopy(DEFAULT_SETTINGS)
                _deep_update(merged, stored)
                _settings = merged
            except (json.JSONDecodeError, OSError) as e:
                # Corrupt or unreadable — fall back to defaults but keep running.
                print(f"[settings] Failed to load {path}: {e}. Using defaults.")
                _settings = deepcopy(DEFAULT_SETTINGS)
        else:
            _settings = deepcopy(DEFAULT_SETTINGS)
            save_settings()  # Write defaults so user can edit the file directly.
    return deepcopy(_settings)


def save_settings() -> None:
    """Persist current settings to disk."""
    path = _settings_path()
    with _lock:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(_settings, f, indent=2, ensure_ascii=False)
        except OSError as e:
            print(f"[settings] Failed to save {path}: {e}")


def get_settings() -> Dict[str, Any]:
    """Return a deep copy of the current settings."""
    with _lock:
        return deepcopy(_settings)


def get_setting(key: str, default: Any = None) -> Any:
    """Get a single setting value by dot-notation path, e.g. 'ollama.host'."""
    with _lock:
        keys = key.split(".")
        val = _settings
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default
        return deepcopy(val)


def update_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Apply a flat or nested dict of updates and persist."""
    global _settings
    with _lock:
        _deep_update(_settings, updates)
        save_settings()
        return deepcopy(_settings)


def reset_settings() -> Dict[str, Any]:
    """Reset everything to factory defaults and persist."""
    global _settings
    with _lock:
        _settings = deepcopy(DEFAULT_SETTINGS)
        save_settings()
        return deepcopy(_settings)


def _deep_update(base: Dict[str, Any], updates: Dict[str, Any]) -> None:
    """Recursively merge updates into base (in-place)."""
    for key, value in updates.items():
        if isinstance(value, dict) and key in base and isinstance(base[key], dict):
            _deep_update(base[key], value)
        else:
            base[key] = value


# Auto-load on module import so settings are always available.
load_settings()
