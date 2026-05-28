"""
notifications.py
================
Webhook notification system for marketplace events.
Supports Discord, Slack, and generic HTTP webhooks.
"""
import json
import uuid
import time
import urllib.request
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from .billing_db import _get_db

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _init_webhooks_table():
    with _get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS webhook_subscriptions (
            webhook_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            webhook_type TEXT NOT NULL DEFAULT 'generic',
            events TEXT NOT NULL DEFAULT 'all',
            active INTEGER NOT NULL DEFAULT 1,
            created_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
        );
        CREATE INDEX IF NOT EXISTS idx_webhooks_user ON webhook_subscriptions(user_id);
        """)
        conn.commit()


_init_webhooks_table()


class WebhookSubscription(BaseModel):
    user_id: str
    name: str
    url: str
    webhook_type: str = "generic"  # generic | discord | slack
    events: str = "all"  # comma-separated: claimed,submit_review,approved,rejected,payout


class TestWebhookRequest(BaseModel):
    url: str
    webhook_type: str = "generic"


def _send_discord(url: str, title: str, description: str, color: int = 0x00ff00):
    payload = {
        "embeds": [{
            "title": title,
            "description": description,
            "color": color,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }]
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={
        "Content-Type": "application/json"
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 204
    except Exception:
        return False


def _send_slack(url: str, text: str):
    payload = {"text": text}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={
        "Content-Type": "application/json"
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _send_generic(url: str, payload: dict):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={
        "Content-Type": "application/json"
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status in (200, 201, 202, 204)
    except Exception:
        return False


def notify(event_type: str, task: dict, extra: Optional[dict] = None):
    """Fire webhooks for all subscribers interested in this event."""
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM webhook_subscriptions WHERE active = 1"
        ).fetchall()

    for sub in rows:
        events = sub["events"].split(",")
        if "all" not in events and event_type not in events:
            continue

        url = sub["url"]
        wtype = sub["webhook_type"]

        if wtype == "discord":
            title = f"SimplePod: {event_type.replace('_', ' ').title()}"
            desc = f"**Task:** {task.get('goal', 'N/A')[:100]}\n"
            desc += f"**Bounty:** ${task.get('bounty', 0):.2f}\n"
            if extra:
                for k, v in extra.items():
                    desc += f"**{k.replace('_', ' ').title()}:** {v}\n"
            color = 0x00ff00 if event_type in ("approved", "payout") else 0xffaa00
            _send_discord(url, title, desc, color)

        elif wtype == "slack":
            text = f"*SimplePod Notification: {event_type.replace('_', ' ').title()}*\n"
            text += f"> Task: {task.get('goal', 'N/A')[:100]}\n"
            text += f"> Bounty: ${task.get('bounty', 0):.2f}\n"
            if extra:
                for k, v in extra.items():
                    text += f"> {k.replace('_', ' ').title()}: {v}\n"
            _send_slack(url, text)

        else:
            payload = {
                "event": event_type,
                "timestamp": time.time(),
                "task": {
                    "task_id": task.get("task_id"),
                    "goal": task.get("goal"),
                    "bounty": task.get("bounty"),
                    "status": task.get("status"),
                    "claimed_by": task.get("claimed_by"),
                    "claimed_by_name": task.get("claimed_by_name"),
                },
                "extra": extra or {},
            }
            _send_generic(url, payload)


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
@router.post("/webhooks")
def create_webhook(req: WebhookSubscription):
    webhook_id = str(uuid.uuid4())
    with _get_db() as conn:
        conn.execute(
            """INSERT INTO webhook_subscriptions
               (webhook_id, user_id, name, url, webhook_type, events)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (webhook_id, req.user_id, req.name, req.url, req.webhook_type, req.events)
        )
        conn.commit()
    return {"success": True, "webhook_id": webhook_id}


@router.get("/webhooks/{user_id}")
def list_webhooks(user_id: str):
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM webhook_subscriptions WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        ).fetchall()
    return {"webhooks": [dict(r) for r in rows]}


@router.delete("/webhooks/{webhook_id}")
def delete_webhook(webhook_id: str, user_id: str):
    with _get_db() as conn:
        conn.execute(
            "DELETE FROM webhook_subscriptions WHERE webhook_id = ? AND user_id = ?",
            (webhook_id, user_id)
        )
        conn.commit()
    return {"success": True}


@router.post("/webhooks/test")
def test_webhook(req: TestWebhookRequest):
    """Send a test notification to verify webhook works."""
    if req.webhook_type == "discord":
        ok = _send_discord(req.url, "SimplePod Test", "Your webhook is working!", 0x00ff00)
    elif req.webhook_type == "slack":
        ok = _send_slack(req.url, "*SimplePod Test*\nYour webhook is working!")
    else:
        ok = _send_generic(req.url, {"event": "test", "message": "Your webhook is working!"})
    return {"success": ok, "webhook_type": req.webhook_type}


@router.post("/webhooks/{webhook_id}/toggle")
def toggle_webhook(webhook_id: str, user_id: str):
    with _get_db() as conn:
        row = conn.execute(
            "SELECT active FROM webhook_subscriptions WHERE webhook_id = ? AND user_id = ?",
            (webhook_id, user_id)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Webhook not found")
        new_state = 0 if row["active"] else 1
        conn.execute(
            "UPDATE webhook_subscriptions SET active = ? WHERE webhook_id = ?",
            (new_state, webhook_id)
        )
        conn.commit()
    return {"success": True, "active": bool(new_state)}
