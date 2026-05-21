"""
health_checker.py

ELI5: This is the building inspector who walks up to each drawing station,
      knocks on the door (HTTP probe), asks for a quick sketch (tiny prompt),
      times how long the first line takes (TTFT), and peeks at the plotter
      (GPU) to see how much paper (VRAM) is left. Then slaps a green,
      yellow, or red sticker on the station dossier.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

import httpx
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────────────────────────────────────

class HealthStatus(str, Enum):
    """ELI5: The sticker colors the inspector puts on each station."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class GPUInfo(BaseModel):
    """ELI5: A quick snapshot of the plotter's paper tray and motor temperature."""
    name: Optional[str] = Field(None, description="GPU model name")
    utilization_percent: Optional[float] = Field(None, description="GPU compute util %")
    vram_total_mb: Optional[float] = Field(None, description="Total VRAM in MB")
    vram_used_mb: Optional[float] = Field(None, description="Used VRAM in MB")
    vram_free_mb: Optional[float] = Field(None, description="Free VRAM in MB")
    temperature_c: Optional[float] = Field(None, description="GPU temperature in °C")


class HealthReport(BaseModel):
    """ELI5: The inspector's clipboard after visiting one station."""
    url: str = Field(..., description="Endpoint URL probed")
    provider: str = Field(..., description="Provider name (ollama | lmstudio)")
    status: HealthStatus = Field(default=HealthStatus.OFFLINE, description="Derived health status")
    latency_ms: Optional[float] = Field(None, description="HTTP round-trip for model-list probe")
    ttft_ms: Optional[float] = Field(None, description="Time-to-first-token for tiny prompt")
    throughput_tps: Optional[float] = Field(None, description="Tokens per second observed")
    gpu_info: Optional[GPUInfo] = Field(None, description="GPU snapshot if available")
    model_count: int = Field(0, description="Number of models reported by endpoint")
    error_message: Optional[str] = Field(None, description="Human-readable failure reason")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When the inspection happened")


# ──────────────────────────────────────────────────────────────────────────────
# GPU Inspector
# ──────────────────────────────────────────────────────────────────────────────

async def _check_gpu_local() -> Optional[GPUInfo]:
    """ELI5: Peek at the plotter control panel via nvidia-smi to see paper levels.
    
    Returns None if nvidia-smi isn't installed (e.g., running on a laptop
    with no plotter at all).
    """
    if shutil.which("nvidia-smi") is None:
        return None

    try:
        proc = await asyncio.create_subprocess_exec(
            "nvidia-smi",
            "--query-gpu=name,utilization.gpu,memory.total,memory.used,memory.free,temperature.gpu",
            "--format=csv,noheader,nounits",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode != 0 or not stdout:
            return None

        line = stdout.decode("utf-8").strip().split("\n")[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            return None

        def _to_float(val: str) -> Optional[float]:
            try:
                return float(val)
            except ValueError:
                return None

        total_mb = _to_float(parts[2])
        used_mb = _to_float(parts[3])
        free_mb = _to_float(parts[4])

        return GPUInfo(
            name=parts[0] or None,
            utilization_percent=_to_float(parts[1]),
            vram_total_mb=total_mb,
            vram_used_mb=used_mb,
            vram_free_mb=free_mb,
            temperature_c=_to_float(parts[5]),
        )
    except Exception:
        # ELI5: Plotter panel is locked; move on without the paper count.
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Endpoint Probing
# ──────────────────────────────────────────────────────────────────────────────

async def _probe_ollama_tags(client: httpx.AsyncClient, url: str) -> tuple[bool, int, float, Optional[str]]:
    """ELI5: Ask an Ollama station 'Hey, what templates do you have loaded?'
    
    Returns (ok, model_count, latency_ms, error_msg).
    """
    probe_url = f"{url.rstrip('/')}/api/tags"
    start = time.perf_counter()
    try:
        resp = await client.get(probe_url, timeout=10.0)
        latency_ms = (time.perf_counter() - start) * 1000
        if resp.status_code != 200:
            return False, 0, latency_ms, f"HTTP {resp.status_code}"
        data = resp.json()
        models = data.get("models", [])
        return True, len(models), latency_ms, None
    except httpx.TimeoutException:
        return False, 0, (time.perf_counter() - start) * 1000, "Timeout fetching /api/tags"
    except Exception as exc:
        return False, 0, (time.perf_counter() - start) * 1000, str(exc)


async def _probe_lmstudio_models(client: httpx.AsyncClient, url: str) -> tuple[bool, int, float, Optional[str]]:
    """ELI5: Ask an LM Studio station 'Hey, what templates do you have loaded?'
    
    Returns (ok, model_count, latency_ms, error_msg).
    """
    probe_url = f"{url.rstrip('/')}/v1/models"
    start = time.perf_counter()
    try:
        resp = await client.get(probe_url, timeout=10.0)
        latency_ms = (time.perf_counter() - start) * 1000
        if resp.status_code != 200:
            return False, 0, latency_ms, f"HTTP {resp.status_code}"
        data = resp.json()
        models = data.get("data", []) if isinstance(data, dict) else []
        return True, len(models), latency_ms, None
    except httpx.TimeoutException:
        return False, 0, (time.perf_counter() - start) * 1000, "Timeout fetching /v1/models"
    except Exception as exc:
        return False, 0, (time.perf_counter() - start) * 1000, str(exc)


async def _test_inference_ollama(
    client: httpx.AsyncClient, url: str
) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """ELI5: Hand the Ollama station a scrap of paper with 'hi' and time the first
    line of the sketch (TTFT) and how fast it draws (throughput).
    
    Returns (ttft_ms, throughput_tps, error_msg).
    """
    gen_url = f"{url.rstrip('/')}/api/generate"
    payload: Dict[str, Any] = {
        "model": "",  # Ollama will use default / loaded model if empty
        "prompt": "hi",
        "stream": False,
        "options": {"num_predict": 8},
    }
    start = time.perf_counter()
    try:
        resp = await client.post(gen_url, json=payload, timeout=15.0)
        total_ms = (time.perf_counter() - start) * 1000
        if resp.status_code != 200:
            return None, None, f"Inference HTTP {resp.status_code}"
        data = resp.json()
        # Ollama doesn't expose per-token timing in the non-stream response,
        # so we approximate TTFT as total time (small prompt) and throughput
        # by counting tokens in response / total time.
        response_text = data.get("response", "")
        # Rough token count: words + punctuation heuristic
        token_guess = max(1, len(response_text.split()))
        throughput = token_guess / (total_ms / 1000.0) if total_ms > 0 else None
        return total_ms, throughput, None
    except httpx.TimeoutException:
        return None, None, "Inference timeout"
    except Exception as exc:
        return None, None, str(exc)


async def _test_inference_lmstudio(
    client: httpx.AsyncClient, url: str
) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """ELI5: Hand the LM Studio station a scrap of paper with 'hi' and time the first
    line of the sketch (TTFT) and how fast it draws (throughput).
    
    Returns (ttft_ms, throughput_tps, error_msg).
    """
    chat_url = f"{url.rstrip('/')}/v1/chat/completions"
    payload: Dict[str, Any] = {
        "model": "local-model",  # LM Studio ignores this if only one model loaded
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 8,
        "stream": False,
    }
    start = time.perf_counter()
    try:
        resp = await client.post(chat_url, json=payload, timeout=15.0)
        total_ms = (time.perf_counter() - start) * 1000
        if resp.status_code != 200:
            return None, None, f"Inference HTTP {resp.status_code}"
        data = resp.json()
        choices = data.get("choices", [])
        content = ""
        if choices:
            content = choices[0].get("message", {}).get("content", "")
        token_guess = max(1, len(content.split()))
        throughput = token_guess / (total_ms / 1000.0) if total_ms > 0 else None
        return total_ms, throughput, None
    except httpx.TimeoutException:
        return None, None, "Inference timeout"
    except Exception as exc:
        return None, None, str(exc)


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

async def probe_endpoint(url: str, provider: str) -> HealthReport:
    """ELI5: The full building-inspector routine for one drawing station.
    
    1. Knock on the door and ask for the template list.
    2. Hand them a scrap paper with 'hi' and time the sketch.
    3. Peek at the plotter's paper tray (GPU) if we're on the same floor.
    4. Slap a sticker: green, yellow, or red.
    """
    report = HealthReport(url=url, provider=provider)

    async with httpx.AsyncClient() as client:
        # ── Step 1: Can we even reach the station? ──
        if provider.lower() == "ollama":
            ok, model_count, latency_ms, err = await _probe_ollama_tags(client, url)
        elif provider.lower() == "lmstudio":
            ok, model_count, latency_ms, err = await _probe_lmstudio_models(client, url)
        else:
            report.error_message = f"Unknown provider: {provider}"
            report.status = HealthStatus.OFFLINE
            return report

        report.latency_ms = latency_ms
        report.model_count = model_count

        if not ok:
            report.error_message = err
            report.status = HealthStatus.OFFLINE
            return report

        # ── Step 2: Ask for a quick sketch ──
        if provider.lower() == "ollama":
            ttft, tps, inf_err = await _test_inference_ollama(client, url)
        else:
            ttft, tps, inf_err = await _test_inference_lmstudio(client, url)

        report.ttft_ms = ttft
        report.throughput_tps = tps
        if inf_err:
            # ELI5: Station answered the door but couldn't draw a sketch — yellow sticker.
            report.error_message = inf_err
            report.status = HealthStatus.DEGRADED
            return report

        # ── Step 3: Check plotter paper levels (GPU) ──
        gpu_info = await _check_gpu_local()
        report.gpu_info = gpu_info

        # ── Step 4: Pick the sticker color ──
        # ELI5: Green if everything looks good and fast enough.
        #       Yellow if it's sluggish or low on paper.
        #       Red we already handled above.
        if report.latency_ms is not None and report.latency_ms > 5000:
            report.status = HealthStatus.DEGRADED
            report.error_message = report.error_message or "High latency on model list"
        elif gpu_info and gpu_info.vram_free_mb is not None and gpu_info.vram_free_mb < 512:
            report.status = HealthStatus.DEGRADED
            report.error_message = report.error_message or "Low VRAM"
        elif report.ttft_ms is not None and report.ttft_ms > 10000:
            report.status = HealthStatus.DEGRADED
            report.error_message = report.error_message or "Slow inference (high TTFT)"
        else:
            report.status = HealthStatus.HEALTHY

    return report


# ──────────────────────────────────────────────────────────────────────────────
# CLI sanity-check
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    async def _main() -> None:
        target = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:11434"
        prov = sys.argv[2] if len(sys.argv) > 2 else "ollama"
        print(f"🔍 Probing {prov} at {target} …")
        report = await probe_endpoint(target, prov)
        print(report.model_dump_json(indent=2))

    asyncio.run(_main())
