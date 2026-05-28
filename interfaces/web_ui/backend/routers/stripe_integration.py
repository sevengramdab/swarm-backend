"""
stripe_integration.py
=====================
Real payment processing via Stripe.

- Checkout Sessions: Users buy credits with credit cards
- Stripe Connect: Node operators get paid directly
- Webhooks: Handle payment confirmation asynchronously

Set env vars:
    STRIPE_SECRET_KEY=sk_test_...
    STRIPE_PUBLISHABLE_KEY=pk_test_...
    STRIPE_WEBHOOK_SECRET=whsec_...
"""
import os
import uuid
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import JSONResponse

from .billing_db import get_account, update_account, add_transaction

router = APIRouter(prefix="/stripe", tags=["stripe"])

# ---------------------------------------------------------------------------
# Stripe client setup
# ---------------------------------------------------------------------------
try:
    import stripe
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "sk_test_placeholder")
    STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "pk_test_placeholder")
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_ENABLED = "sk_test" in stripe.api_key or "sk_live" in stripe.api_key
except ImportError:
    stripe = None
    STRIPE_ENABLED = False

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:8000")


def _require_stripe():
    if not STRIPE_ENABLED or stripe is None:
        raise HTTPException(status_code=503, detail="Stripe payments are not configured. Set STRIPE_SECRET_KEY env var.")


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class CreateCheckoutRequest(BaseModel):
    user_id: str
    amount: float = Field(..., gt=0, le=1000, description="Dollar amount to purchase")


class CreateConnectRequest(BaseModel):
    user_id: str
    email: str


# ---------------------------------------------------------------------------
# Checkout Sessions (Buy Credits)
# ---------------------------------------------------------------------------
@router.post("/checkout/create")
def create_checkout_session(req: CreateCheckoutRequest):
    """Create a Stripe Checkout Session for buying credits."""
    _require_stripe()
    user_id = req.user_id
    amount_cents = int(req.amount * 100)

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"SimplePod Credits — ${req.amount:.2f}"},
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{FRONTEND_URL}/earnings?payment=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/earnings?payment=cancelled",
            metadata={"user_id": user_id, "type": "credit_deposit"},
        )
        return {"success": True, "session_id": session.id, "checkout_url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/checkout/status/{session_id}")
def get_checkout_status(session_id: str):
    """Get the status of a checkout session."""
    _require_stripe()
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        return {
            "session_id": session.id,
            "status": session.status,
            "payment_status": session.payment_status,
            "amount_total": session.amount_total / 100 if session.amount_total else 0,
            "metadata": session.metadata,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Stripe Connect (Node Operator Onboarding)
# ---------------------------------------------------------------------------
@router.post("/connect/onboard")
def connect_onboard(req: CreateConnectRequest):
    """Create a Stripe Connect Express account for a node operator."""
    _require_stripe()
    try:
        account = stripe.Account.create(
            type="express",
            email=req.email,
            metadata={"user_id": req.user_id},
            capabilities={"transfers": {"requested": True}},
        )
        # Create account link for onboarding
        link = stripe.AccountLink.create(
            account=account.id,
            refresh_url=f"{FRONTEND_URL}/earnings?connect=refresh",
            return_url=f"{FRONTEND_URL}/earnings?connect=success",
            type="account_onboarding",
        )
        return {
            "success": True,
            "account_id": account.id,
            "onboarding_url": link.url,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connect/account/{account_id}")
def get_connect_account(account_id: str):
    """Get Stripe Connect account status."""
    _require_stripe()
    try:
        account = stripe.Account.retrieve(account_id)
        return {
            "account_id": account.id,
            "charges_enabled": account.charges_enabled,
            "payouts_enabled": account.payouts_enabled,
            "details_submitted": account.details_submitted,
            "email": account.email,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connect/payout")
def create_payout(user_id: str, amount: float, connect_account_id: str):
    """Send a payout to a Stripe Connect account."""
    _require_stripe()
    try:
        transfer = stripe.Transfer.create(
            amount=int(amount * 100),
            currency="usd",
            destination=connect_account_id,
            metadata={"user_id": user_id, "type": "node_payout"},
        )
        return {
            "success": True,
            "transfer_id": transfer.id,
            "amount": amount,
            "status": transfer.status,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Stripe Webhook Handler
# ---------------------------------------------------------------------------
@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: Optional[str] = Header(None)):
    """Handle Stripe webhook events."""
    if not STRIPE_ENABLED or stripe is None:
        return JSONResponse({"status": "stripe_not_configured"}, status_code=200)

    payload = await request.body()
    sig_header = stripe_signature or ""

    try:
        if STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        else:
            event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    event_type = event.get("type", "")

    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        metadata = session.get("metadata", {})
        user_id = metadata.get("user_id")
        amount_dollars = session.get("amount_total", 0) / 100

        if user_id and metadata.get("type") == "credit_deposit":
            acct = get_account(user_id)
            if acct:
                new_credits = acct["credits"] + amount_dollars
                update_account(user_id, credits=new_credits)
                add_transaction(
                    tx_id=str(uuid.uuid4()),
                    tx_type="stripe_deposit",
                    user_id=user_id,
                    amount=amount_dollars,
                    method="stripe",
                )
            print(f"[stripe] Deposit confirmed: {user_id} +${amount_dollars}")

    elif event_type == "transfer.paid":
        transfer = event["data"]["object"]
        metadata = transfer.get("metadata", {})
        user_id = metadata.get("user_id")
        amount_dollars = transfer.get("amount", 0) / 100
        print(f"[stripe] Payout sent: {user_id} ${amount_dollars}")

    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Config / Status
# ---------------------------------------------------------------------------
@router.get("/config")
def stripe_config():
    """Return Stripe publishable key for frontend."""
    return {
        "enabled": STRIPE_ENABLED,
        "publishable_key": STRIPE_PUBLISHABLE_KEY if STRIPE_ENABLED else None,
        "mode": "test" if STRIPE_PUBLISHABLE_KEY.startswith("pk_test") else "live" if STRIPE_ENABLED else None,
    }
