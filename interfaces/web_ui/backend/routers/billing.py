"""
billing.py
==========
Monetization engine for SimplePod Swarm.

Business model:
- Users post tasks with $ bounties
- Node operators earn for completed tasks
- SimplePod takes 15% platform fee
- Automatic pricing based on GPU + complexity
"""
import uuid
import time
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from .billing_db import (
    init_db, get_account, update_account,
    create_task as db_create_task, get_task as db_get_task,
    list_tasks as db_list_tasks, claim_task as db_claim_task,
    complete_task as db_complete_task, cancel_task as db_cancel_task,
    submit_for_review as db_submit_for_review,
    approve_task as db_approve_task, reject_task as db_reject_task,
    set_swarmcoder_task_id, add_transaction, list_transactions,
    get_platform_stats, get_leaderboard,
)

router = APIRouter(prefix="/billing", tags=["billing"])

# Initialize DB on module load
init_db()

# ---------------------------------------------------------------------------
# Pricing Engine
# ---------------------------------------------------------------------------
GPU_MULTIPLIERS = {
    "gtx_1650": 1.0,
    "gtx_1660": 1.1,
    "rtx_2060": 1.2,
    "rtx_3060": 1.3,
    "rtx_3070": 1.4,
    "rtx_3080": 1.6,
    "rtx_3090": 1.8,
    "rtx_4060": 1.4,
    "rtx_4070": 1.6,
    "rtx_4080": 1.9,
    "rtx_4090": 2.2,
    "rtx_5070": 2.5,
    "rtx_5080": 2.8,
    "rtx_5090": 3.2,
    "unknown": 1.0,
}

COMPLEXITY_MULTIPLIERS = {
    "simple": 1.0,
    "medium": 1.5,
    "complex": 3.0,
}

PLATFORM_FEE_PCT = 0.15
BASE_TASK_COST = 0.50
VRAM_RATE_PER_MB = 0.0001
MIN_BOUNTY = 0.50


def calculate_task_price(vram_mb: int, gpu_type: str = "unknown", complexity: str = "medium") -> dict:
    """Calculate task pricing breakdown."""
    gpu_mult = GPU_MULTIPLIERS.get(gpu_type.lower().replace(" ", "_"), 1.0)
    comp_mult = COMPLEXITY_MULTIPLIERS.get(complexity.lower(), 1.5)
    vram_cost = vram_mb * VRAM_RATE_PER_MB
    subtotal = (BASE_TASK_COST + vram_cost) * gpu_mult * comp_mult
    platform_fee = round(subtotal * PLATFORM_FEE_PCT, 2)
    node_earnings = round(subtotal - platform_fee, 2)
    total = round(subtotal, 2)
    return {
        "base_cost": BASE_TASK_COST,
        "vram_cost": round(vram_cost, 2),
        "gpu_multiplier": gpu_mult,
        "complexity_multiplier": comp_mult,
        "subtotal": subtotal,
        "platform_fee": platform_fee,
        "node_earnings": node_earnings,
        "total": total,
    }


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class AccountResponse(BaseModel):
    user_id: str
    credits: float
    total_spent: float
    total_earned: float
    tasks_posted: int
    tasks_completed: int


class DepositRequest(BaseModel):
    user_id: str
    amount: float = Field(..., gt=0, description="Amount to add to balance")
    payment_method: str = "stripe"  # stripe | crypto | paypal


class WithdrawRequest(BaseModel):
    user_id: str
    amount: float = Field(..., gt=0)
    destination: str = "stripe_connect"


class PriceEstimateRequest(BaseModel):
    vram_mb: int = 4096
    gpu_type: str = "gtx_1650"
    complexity: str = "medium"


class BountyTaskRequest(BaseModel):
    user_id: str
    goal: str
    bounty: float = Field(..., ge=MIN_BOUNTY, description="Dollar amount for this task")
    gpu_preference: Optional[str] = None
    complexity: str = "medium"


class ClaimTaskRequest(BaseModel):
    node_id: str
    node_name: str


class CompleteTaskRequest(BaseModel):
    result_summary: str = ""


# ---------------------------------------------------------------------------
# Account Management
# ---------------------------------------------------------------------------
@router.get("/account/{user_id}", response_model=AccountResponse)
def get_account_endpoint(user_id: str):
    acct = get_account(user_id)
    if acct is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return acct


@router.post("/account/{user_id}/deposit")
def deposit(user_id: str, req: DepositRequest):
    """Add credits (mock — wire up Stripe in production)."""
    acct = get_account(user_id)
    if acct is None:
        raise HTTPException(status_code=404, detail="Account not found")
    new_credits = acct["credits"] + req.amount
    update_account(user_id, credits=new_credits)
    tx = add_transaction(
        tx_id=str(uuid.uuid4()),
        tx_type="deposit",
        user_id=user_id,
        amount=req.amount,
        method=req.payment_method,
    )
    return {"success": True, "new_balance": new_credits, "tx_id": tx["tx_id"]}


@router.post("/account/{user_id}/withdraw")
def withdraw(user_id: str, req: WithdrawRequest):
    """Cash out earnings (mock — wire up Stripe Connect in production)."""
    acct = get_account(user_id)
    if acct is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if acct["total_earned"] < req.amount:
        raise HTTPException(status_code=400, detail="Insufficient earnings")
    new_earned = acct["total_earned"] - req.amount
    update_account(user_id, total_earned=new_earned)
    tx = add_transaction(
        tx_id=str(uuid.uuid4()),
        tx_type="withdrawal",
        user_id=user_id,
        amount=-req.amount,
        method=req.destination,
    )
    return {"success": True, "remaining_earnings": new_earned, "tx_id": tx["tx_id"]}


# ---------------------------------------------------------------------------
# Pricing Engine
# ---------------------------------------------------------------------------
@router.post("/price-estimate")
def price_estimate(req: PriceEstimateRequest):
    """Get automatic pricing for a task before posting."""
    return calculate_task_price(req.vram_mb, req.gpu_type, req.complexity)


@router.get("/pricing-table")
def pricing_table():
    """Show pricing for all GPU tiers."""
    results = []
    for gpu, mult in sorted(GPU_MULTIPLIERS.items(), key=lambda x: -x[1]):
        simple = calculate_task_price(4096, gpu, "simple")
        medium = calculate_task_price(8192, gpu, "medium")
        complex_p = calculate_task_price(16384, gpu, "complex")
        results.append({
            "gpu": gpu,
            "multiplier": mult,
            "example_4gb_simple": simple["total"],
            "example_8gb_medium": medium["total"],
            "example_16gb_complex": complex_p["total"],
        })
    return {"gpus": results, "platform_fee_pct": PLATFORM_FEE_PCT * 100}


# ---------------------------------------------------------------------------
# Task Marketplace (Bounties)
# ---------------------------------------------------------------------------
@router.post("/marketplace/post")
def post_bounty(req: BountyTaskRequest):
    """Post a task with a dollar bounty. Credits are held in escrow."""
    acct = get_account(req.user_id)
    if acct is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if acct["credits"] < req.bounty:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient credits. Balance: ${acct['credits']:.2f}, Required: ${req.bounty:.2f}"
        )

    # Deduct from balance (escrow)
    new_credits = acct["credits"] - req.bounty
    new_spent = acct["total_spent"] + req.bounty
    new_posted = acct["tasks_posted"] + 1
    update_account(req.user_id, credits=new_credits, total_spent=new_spent, tasks_posted=new_posted)

    task_id = str(uuid.uuid4())
    task = db_create_task(
        task_id=task_id,
        user_id=req.user_id,
        goal=req.goal,
        bounty=req.bounty,
        complexity=req.complexity,
        gpu_preference=req.gpu_preference,
    )
    add_transaction(
        tx_id=str(uuid.uuid4()),
        tx_type="escrow_hold",
        user_id=req.user_id,
        task_id=task_id,
        amount=-req.bounty,
    )
    return {"success": True, "task": task, "remaining_credits": new_credits}


@router.get("/marketplace/tasks")
def list_marketplace(status: Optional[str] = None):
    """List open bounties."""
    tasks = db_list_tasks(status=status)
    return {"tasks": tasks}


@router.get("/marketplace/task/{task_id}")
def get_marketplace_task(task_id: str):
    task = db_get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/marketplace/{task_id}/claim")
def claim_task(task_id: str, req: ClaimTaskRequest):
    """A node claims an open bounty."""
    task = db_get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] != "open":
        raise HTTPException(status_code=400, detail=f"Task already {task['status']}")

    updated = db_claim_task(task_id, req.node_id, req.node_name)
    if updated is None or updated["status"] != "claimed":
        raise HTTPException(status_code=400, detail="Failed to claim task")

    # Auto-submit to SwarmCoder for execution
    try:
        from core.simpleswarm.swarm_coder import SwarmCoder
        workspace = f"marketplace_tasks/{task_id}"
        import os
        os.makedirs(workspace, exist_ok=True)
        coder = SwarmCoder(project_dir=workspace)
        sc_task = coder.submit_task(task["goal"])
        set_swarmcoder_task_id(task_id, sc_task.task_id)
    except Exception as e:
        print(f"[billing] SwarmCoder auto-submit failed for {task_id}: {e}")

    return {"success": True, "task": updated}


class SubmitReviewRequest(BaseModel):
    result_summary: str = ""


class ReviewDecisionRequest(BaseModel):
    user_id: str


@router.post("/marketplace/{task_id}/submit-review")
def submit_for_review(task_id: str, req: SubmitReviewRequest):
    """Node submits completed work for poster review."""
    task = db_get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] != "claimed":
        raise HTTPException(status_code=400, detail="Task not claimed")

    updated = db_submit_for_review(task_id, req.result_summary)
    return {"success": True, "task": updated, "message": "Work submitted for review. Poster must approve before payout."}


@router.post("/marketplace/{task_id}/approve")
def approve_task(task_id: str, req: ReviewDecisionRequest):
    """Poster approves work — releases bounty to node minus platform fee."""
    task = db_get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] != "pending_review":
        raise HTTPException(status_code=400, detail="Task not pending review")
    if task["user_id"] != req.user_id:
        raise HTTPException(status_code=403, detail="Only the task poster can approve")

    bounty = task["bounty"]
    fee = round(bounty * PLATFORM_FEE_PCT, 2)
    node_payout = round(bounty - fee, 2)

    # Pay the node operator
    node_acct = get_account(task["claimed_by"])
    if node_acct:
        new_earned = node_acct["total_earned"] + node_payout
        new_credits = node_acct["credits"] + node_payout
        new_completed = node_acct["tasks_completed"] + 1
        update_account(
            task["claimed_by"],
            total_earned=new_earned,
            credits=new_credits,
            tasks_completed=new_completed,
        )

    updated = db_approve_task(task_id, node_payout, fee)
    add_transaction(
        tx_id=str(uuid.uuid4()),
        tx_type="payout",
        user_id=task["claimed_by"],
        task_id=task_id,
        amount=node_payout,
        fee=fee,
    )

    return {
        "success": True,
        "task": updated,
        "node_payout": node_payout,
        "platform_fee": fee,
    }


@router.post("/marketplace/{task_id}/reject")
def reject_task(task_id: str, req: ReviewDecisionRequest):
    """Poster rejects work — task goes back to open for another node."""
    task = db_get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] != "pending_review":
        raise HTTPException(status_code=400, detail="Task not pending review")
    if task["user_id"] != req.user_id:
        raise HTTPException(status_code=403, detail="Only the task poster can reject")

    updated = db_reject_task(task_id)
    return {"success": True, "task": updated, "message": "Work rejected. Task is back open for claiming."}


@router.post("/marketplace/{task_id}/complete")
def complete_task(task_id: str, req: CompleteTaskRequest):
    """Legacy: Mark task complete directly (admin/auto-approve)."""
    task = db_get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] != "claimed":
        raise HTTPException(status_code=400, detail="Task not claimed")

    bounty = task["bounty"]
    fee = round(bounty * PLATFORM_FEE_PCT, 2)
    node_payout = round(bounty - fee, 2)

    # Pay the node operator
    node_acct = get_account(task["claimed_by"])
    if node_acct:
        new_earned = node_acct["total_earned"] + node_payout
        new_credits = node_acct["credits"] + node_payout
        new_completed = node_acct["tasks_completed"] + 1
        update_account(
            task["claimed_by"],
            total_earned=new_earned,
            credits=new_credits,
            tasks_completed=new_completed,
        )

    updated = db_complete_task(task_id, req.result_summary, node_payout, fee)
    add_transaction(
        tx_id=str(uuid.uuid4()),
        tx_type="payout",
        user_id=task["claimed_by"],
        task_id=task_id,
        amount=node_payout,
        fee=fee,
    )

    return {
        "success": True,
        "task": updated,
        "node_payout": node_payout,
        "platform_fee": fee,
    }


@router.post("/marketplace/{task_id}/cancel")
def cancel_task(task_id: str, user_id: str):
    """Cancel an open task — refund bounty to poster."""
    task = db_get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] != "open":
        raise HTTPException(status_code=400, detail="Can only cancel open tasks")
    if task["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your task")

    # Refund
    acct = get_account(user_id)
    if acct:
        new_credits = acct["credits"] + task["bounty"]
        new_spent = acct["total_spent"] - task["bounty"]
        new_posted = acct["tasks_posted"] - 1
        update_account(user_id, credits=new_credits, total_spent=new_spent, tasks_posted=new_posted)

    updated = db_cancel_task(task_id, user_id)
    add_transaction(
        tx_id=str(uuid.uuid4()),
        tx_type="refund",
        user_id=user_id,
        task_id=task_id,
        amount=task["bounty"],
    )
    return {"success": True, "refund": task["bounty"], "task": updated}


# ---------------------------------------------------------------------------
# Earnings & Revenue Dashboard
# ---------------------------------------------------------------------------
@router.get("/earnings/{user_id}")
def get_earnings(user_id: str):
    """Get earnings breakdown for a user/node."""
    acct = get_account(user_id)
    if acct is None:
        raise HTTPException(status_code=404, detail="Account not found")
    completed_tasks = db_list_tasks(status=None)
    completed_tasks = [t for t in completed_tasks if t.get("claimed_by") == user_id and t["status"] == "completed"]
    return {
        "user_id": user_id,
        "total_earned": acct["total_earned"],
        "total_spent": acct["total_spent"],
        "current_balance": acct["credits"],
        "tasks_completed": acct["tasks_completed"],
        "tasks_posted": acct["tasks_posted"],
        "completed_tasks": completed_tasks,
    }


@router.get("/platform/revenue")
def platform_revenue():
    """Platform-wide revenue stats."""
    return get_platform_stats()


@router.get("/leaderboard")
def leaderboard():
    """Top earners in the swarm."""
    return {"top_earners": get_leaderboard()}


@router.get("/transactions/{user_id}")
def user_transactions(user_id: str, limit: int = 50):
    """Get transaction history for a user."""
    txs = list_transactions(user_id=user_id, limit=limit)
    return {"transactions": txs}
