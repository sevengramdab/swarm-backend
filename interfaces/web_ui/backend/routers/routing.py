#!/usr/bin/env python3
"""
routers/routing.py
==================
Main Breaker control endpoints.

ELI5: These are the controls on the automatic transfer switch.
      You can read the current position, move the slider,
      or lock it to SOLAR or GRID.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_main_breaker, get_swarm_orchestrator
from ..models import InferRequest, InferResponse, RoutingConfigResponse, SetThresholdRequest

router = APIRouter(prefix="/routing", tags=["routing"])


@router.get("/config", response_model=RoutingConfigResponse)
async def routing_config(breaker=Depends(get_main_breaker)) -> RoutingConfigResponse:
    """Read the current position of the Main Breaker slider."""
    if hasattr(breaker, "_mode") and hasattr(breaker, "_threshold"):
        healthy = []
        tripped = []
        if hasattr(breaker, "tier_manager"):
            tiers = await breaker.tier_manager.get_all_tiers()
            for t in tiers:
                if t.health_status.value == "healthy":
                    healthy.append(t.name)
                else:
                    tripped.append(t.name)
        return RoutingConfigResponse(
            mode=breaker._mode.value,
            threshold=breaker._threshold,
            healthy_tiers=healthy,
            tripped_tiers=tripped,
        )
    raise HTTPException(status_code=503, detail="Main breaker not ready")


@router.post("/threshold")
async def set_threshold(req: SetThresholdRequest, breaker=Depends(get_main_breaker)) -> dict:
    """Move the Main Breaker slider."""
    if hasattr(breaker, "set_threshold"):
        await breaker.set_threshold(req.threshold)
        return {"threshold": req.threshold, "mode": "auto"}
    raise HTTPException(status_code=501, detail="Threshold control not available")


@router.post("/force-local")
async def force_local(breaker=Depends(get_main_breaker)) -> dict:
    """Lock the transfer switch to SOLAR."""
    if hasattr(breaker, "force_local"):
        await breaker.force_local()
        return {"mode": "force_local"}
    raise HTTPException(status_code=501, detail="Force local not available")


@router.post("/force-cloud")
async def force_cloud(breaker=Depends(get_main_breaker)) -> dict:
    """Lock the transfer switch to GRID."""
    if hasattr(breaker, "force_cloud"):
        await breaker.force_cloud()
        return {"mode": "force_cloud"}
    raise HTTPException(status_code=501, detail="Force cloud not available")


@router.post("/auto")
async def auto_balance(breaker=Depends(get_main_breaker)) -> dict:
    """Unlock the transfer switch — let the smart controller decide."""
    if hasattr(breaker, "auto_balance"):
        await breaker.auto_balance()
        return {"mode": "auto"}
    raise HTTPException(status_code=501, detail="Auto balance not available")


@router.post("/infer", response_model=InferResponse)
async def infer(
    req: InferRequest,
    breaker=Depends(get_main_breaker),
    orch=Depends(get_swarm_orchestrator),
) -> InferResponse:
    """Submit a new appliance and let the panel decide which circuit."""
    if hasattr(breaker, "route"):
        decision = await breaker.route(req)

        # Actually queue the task in the real orchestrator so agents process it.
        task_id = None
        if hasattr(orch, "submit_inference"):
            task_id = orch.submit_inference(
                prompt=req.prompt,
                tier=decision.tier,
                node_id=decision.node_id,
                model=req.model_hint or decision.model,
                complexity_score=decision.complexity.overall,
                system_prompt=req.system_prompt,
                temperature=req.temperature,
                messages=[m.model_dump() if hasattr(m, "model_dump") else dict(m) for m in (req.messages or [])],
                mode=req.mode,
            )

        return InferResponse(
            request_id=decision.request_id,
            tier=decision.tier,
            node_id=decision.node_id,
            model=decision.model,
            complexity_score=decision.complexity.overall,
            reason=f"{decision.reason} | queued as task {task_id}" if task_id else decision.reason,
            estimated_cost=decision.estimated_cost,
            estimated_latency_ms=decision.estimated_latency_ms,
            task_id=task_id,
        )
    raise HTTPException(status_code=501, detail="Inference routing not available")
