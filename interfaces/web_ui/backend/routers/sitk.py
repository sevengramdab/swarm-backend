#!/usr/bin/env python3
"""
routers/sitk.py
===============
SITK deployment endpoints.

ELI5: Like the shipping and receiving desk.
      `POST /sitk/pack` = box up a shipment.
      `POST /sitk/deploy` = hand the box to the courier.
      `GET /sitk/transfers` = track all packages in transit.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..models import SITKTransferStatus

router = APIRouter(prefix="/sitk", tags=["sitk"])

# In-memory transfer tracking until wired to real orchestrator.
_transfers: dict[str, SITKTransferStatus] = {}


@router.post("/pack")
async def pack_payload() -> dict:
    """Box up a shipment."""
    return {"status": "packed", "payload_id": "placeholder"}


@router.post("/deploy")
async def deploy_payload(target_node: str) -> dict:
    """Hand the box to the courier."""
    return {"status": "deployed", "target_node": target_node}


@router.get("/transfers")
async def list_transfers() -> list:
    """Show all packages on the truck."""
    return list(_transfers.values())


@router.get("/transfers/{transfer_id}")
async def get_transfer(transfer_id: str) -> SITKTransferStatus:
    """Track one package."""
    if transfer_id not in _transfers:
        raise HTTPException(status_code=404, detail="Transfer not found")
    return _transfers[transfer_id]
