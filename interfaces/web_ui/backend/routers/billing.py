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

router = APIRouter(prefix="/billing", tags=["billing"])

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
# In-Memory Data Stores (replace with DB in production)
# ---------------------------------------------------------------------------
_accounts: Dict[str, dict] = {}
_marketplace_tasks: Dict[str, dict] = {}
_transactions: List[dict] = []
_platform_revenue = 0.0


def _get_account(user_id: str) -> dict:
    if user_id not in _accounts:
        _accounts[user_id] = {
            "user_id": user_id,
            "credits": 25.0,  # Free starter credits
            "total_spent": 0.0,
            "total_earned": 0.0,
            "tasks_posted": 0,
            "tasks_completed": 0,
            "created_at": time.time(),
        }
    return _accounts[user_id]


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
def get_account(user_id: str):
    return _get_account(user_id)


@router.post("/account/{user_id}/deposit")
def deposit(user_id: str, req: DepositRequest):
    """Add credits (mock — wire up Stripe in production)."""
    acct = _get_account(user_id)
    acct["credits"] += req.amount
    _transactions.append({
        "tx_id": str(uuid.uuid4()),
        "type": "deposit",
        "user_id": user_id,
        "amount": req.amount,
        "method": req.payment_method,
        "timestamp": time.time(),
    })
    return {"success": True, "new_balance": acct["credits"], "tx_id": _transactions[-1]["tx_id"]}


@router.post("/account/{user_id}/withdraw")
def withdraw(user_id: str, req: WithdrawRequest):
    """Cash out earnings (mock — wire up Stripe Connect in production)."""
    acct = _get_account(user_id)
    if acct["total_earned"] < req.amount:
        raise HTTPException(status_code=400, detail="Insufficient earnings")
    acct["total_earned"] -= req.amount
    _transactions.append({
        "tx_id": str(uuid.uuid4()),
        "type": "withdrawal",
        "user_id": user_id,
        "amount": -req.amount,
        "method": req.destination,
        "timestamp": time.time(),
    })
    return {"success": True, "remaining_earnings": acct["total_earned"], "tx_id": _transactions[-1]["tx_id"]}


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
    acct = _get_account(req.user_id)
    if acct["credits"] < req.bounty:
        raise HTTPException(status_code=402, detail=f"Insufficient credits. Balance: ${acct['credits']:.2f}, Required: ${req.bounty:.2f}")

    # Deduct from balance (escrow)
    acct["credits"] -= req.bounty
    acct["total_spent"] += req.bounty
    acct["tasks_posted"] += 1

    task_id = str(uuid.uuid4())
    task = {
        "task_id": task_id,
        "user_id": req.user_id,
        "goal": req.goal,
        "bounty": req.bounty,
        "gpu_preference": req.gpu_preference,
        "complexity": req.complexity,
        "status": "open",  # open | claimed | completed | cancelled
        "claimed_by": None,
        "claimed_at": None,
        "completed_at": None,
        "result_summary": None,
        "created_at": time.time(),
    }
    _marketplace_tasks[task_id] = task
    _transactions.append({
        "tx_id": str(uuid.uuid4()),
        "type": "escrow_hold",
        "user_id": req.user_id,
        "task_id": task_id,
        "amount": -req.bounty,
        "timestamp": time.time(),
    })
    return {"success": True, "task": task, "remaining_credits": acct["credits"]}


@router.get("/marketplace/tasks")
def list_marketplace(status: Optional[str] = None):
    """List open bounties."""
    tasks = list(_marketplace_tasks.values())
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    return {"tasks": sorted(tasks, key=lambda x: -x["bounty"])}


@router.post("/marketplace/{task_id}/claim")
def claim_task(task_id: str, req: ClaimTaskRequest):
    """A node claims an open bounty."""
    if task_id not in _marketplace_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = _marketplace_tasks[task_id]
    if task["status"] != "open":
        raise HTTPException(status_code=400, detail=f"Task already {task['status']}")

    task["status"] = "claimed"
    task["claimed_by"] = req.node_id
    task["claimed_by_name"] = req.node_name
    task["claimed_at"] = time.time()
    return {"success": True, "task": task}


@router.post("/marketplace/{task_id}/complete")
def complete_task(task_id: str, req: CompleteTaskRequest):
    """Mark task complete — release bounty to node minus platform fee."""
    global _platform_revenue

    if task_id not in _marketplace_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = _marketplace_tasks[task_id]
    if task["status"] != "claimed":
        raise HTTPException(status_code=400, detail="Task not claimed")

    bounty = task["bounty"]
    fee = round(bounty * PLATFORM_FEE_PCT, 2)
    node_payout = round(bounty - fee, 2)

    # Pay the node operator
    node_acct = _get_account(task["claimed_by"])
    node_acct["total_earned"] += node_payout
    node_acct["tasks_completed"] += 1
    node_acct["credits"] += node_payout  # earnings go to credit balance

    # Track platform revenue
    _platform_revenue += fee

    task["status"] = "completed"
    task["completed_at"] = time.time()
    task["result_summary"] = req.result_summary
    task["node_payout"] = node_payout
    task["platform_fee"] = fee

    _transactions.append({
        "tx_id": str(uuid.uuid4()),
        "type": "payout",
        "user_id": task["claimed_by"],
        "task_id": task_id,
        "amount": node_payout,
        "fee": fee,
        "timestamp": time.time(),
    })

    return {
        "success": True,
        "task": task,
        "node_payout": node_payout,
        "platform_fee": fee,
    }


@router.post("/marketplace/{task_id}/cancel")
def cancel_task(task_id: str, user_id: str):
    """Cancel an open task — refund bounty to poster."""
    if task_id not in _marketplace_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = _marketplace_tasks[task_id]
    if task["status"] != "open":
        raise HTTPException(status_code=400, detail="Can only cancel open tasks")
    if task["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your task")

    # Refund
    acct = _get_account(user_id)
    acct["credits"] += task["bounty"]
    acct["total_spent"] -= task["bounty"]
    acct["tasks_posted"] -= 1

    task["status"] = "cancelled"
    _transactions.append({
        "tx_id": str(uuid.uuid4()),
        "type": "refund",
        "user_id": user_id,
        "task_id": task_id,
        "amount": task["bounty"],
        "timestamp": time.time(),
    })
    return {"success": True, "refund": task["bounty"], "task": task}


# ---------------------------------------------------------------------------
# Earnings & Revenue Dashboard
# ---------------------------------------------------------------------------
@router.get("/earnings/{user_id}")
def get_earnings(user_id: str):
    """Get earnings breakdown for a user/node."""
    acct = _get_account(user_id)
    completed_tasks = [t for t in _marketplace_tasks.values()
                       if t.get("claimed_by") == user_id and t["status"] == "completed"]
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
    all_tasks = list(_marketplace_tasks.values())
    completed = [t for t in all_tasks if t["status"] == "completed"]
    open_bounties = [t for t in all_tasks if t["status"] == "open"]
    total_bounty_volume = sum(t["bounty"] for t in all_tasks)
    total_paid_out = sum(t.get("node_payout", 0) for t in completed)

    return {
        "platform_revenue": round(_platform_revenue, 2),
        "total_tasks": len(all_tasks),
        "completed_tasks": len(completed),
        "open_bounties": len(open_bounties),
        "total_bounty_volume": round(total_bounty_volume, 2),
        "total_paid_to_nodes": round(total_paid_out, 2),
        "platform_fee_pct": PLATFORM_FEE_PCT * 100,
        "recent_transactions": _transactions[-20:][::-1],
    }


@router.get("/leaderboard")
def leaderboard():
    """Top earners in the swarm."""
    users = sorted(_accounts.values(), key=lambda x: -x["total_earned"])
    return {
        "top_earners": [
            {
                "user_id": u["user_id"],
                "total_earned": u["total_earned"],
                "tasks_completed": u["tasks_completed"],
            }
            for u in users[:10]
        ]
    }
