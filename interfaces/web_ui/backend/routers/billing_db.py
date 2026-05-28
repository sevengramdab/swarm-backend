"""
billing_db.py
=============
SQLite persistence for the billing/marketplace system.
No extra deps — uses Python's built-in sqlite3.
"""
import sqlite3
import json
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

DB_PATH = Path(__file__).parent.parent.parent.parent.parent / "data" / "billing.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


@contextmanager
def _get_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = _dict_factory
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with _get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (
            user_id TEXT PRIMARY KEY,
            credits REAL NOT NULL DEFAULT 25.0,
            total_spent REAL NOT NULL DEFAULT 0.0,
            total_earned REAL NOT NULL DEFAULT 0.0,
            tasks_posted INTEGER NOT NULL DEFAULT 0,
            tasks_completed INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
        );

        CREATE TABLE IF NOT EXISTS marketplace_tasks (
            task_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            goal TEXT NOT NULL,
            bounty REAL NOT NULL,
            gpu_preference TEXT,
            complexity TEXT NOT NULL DEFAULT 'medium',
            status TEXT NOT NULL DEFAULT 'open',
            claimed_by TEXT,
            claimed_by_name TEXT,
            claimed_at REAL,
            completed_at REAL,
            result_summary TEXT,
            node_payout REAL,
            platform_fee REAL,
            swarmcoder_task_id TEXT,
            created_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
        );

        CREATE TABLE IF NOT EXISTS transactions (
            tx_id TEXT PRIMARY KEY,
            tx_type TEXT NOT NULL,
            user_id TEXT NOT NULL,
            task_id TEXT,
            amount REAL NOT NULL,
            fee REAL,
            method TEXT,
            timestamp REAL NOT NULL DEFAULT (strftime('%s', 'now'))
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_status ON marketplace_tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_user ON marketplace_tasks(user_id);
        CREATE INDEX IF NOT EXISTS idx_tx_user ON transactions(user_id);
        CREATE INDEX IF NOT EXISTS idx_tx_task ON transactions(task_id);

        -- Seed default user if not exists
        INSERT OR IGNORE INTO accounts (user_id, credits) VALUES ('user_001', 25.0);
        """)
        conn.commit()


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
def get_account(user_id: str) -> Optional[Dict[str, Any]]:
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO accounts (user_id, credits) VALUES (?, 25.0)",
                (user_id,)
            )
            conn.commit()
            row = conn.execute("SELECT * FROM accounts WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def update_account(user_id: str, **fields) -> Dict[str, Any]:
    with _get_db() as conn:
        allowed = {"credits", "total_spent", "total_earned", "tasks_posted", "tasks_completed"}
        sets = ", ".join(f"{k} = ?" for k in fields if k in allowed)
        vals = [v for k, v in fields.items() if k in allowed]
        if sets:
            conn.execute(f"UPDATE accounts SET {sets} WHERE user_id = ?", (*vals, user_id))
            conn.commit()
        return get_account(user_id)


# ---------------------------------------------------------------------------
# Marketplace Tasks
# ---------------------------------------------------------------------------
def create_task(task_id: str, user_id: str, goal: str, bounty: float,
                complexity: str = "medium", gpu_preference: Optional[str] = None) -> Dict[str, Any]:
    with _get_db() as conn:
        conn.execute(
            """INSERT INTO marketplace_tasks
               (task_id, user_id, goal, bounty, complexity, gpu_preference, status)
               VALUES (?, ?, ?, ?, ?, ?, 'open')""",
            (task_id, user_id, goal, bounty, complexity, gpu_preference)
        )
        conn.commit()
        return get_task(task_id)


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM marketplace_tasks WHERE task_id = ?", (task_id,)).fetchone()
        return dict(row) if row else None


def list_tasks(status: Optional[str] = None) -> List[Dict[str, Any]]:
    with _get_db() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM marketplace_tasks WHERE status = ? ORDER BY bounty DESC",
                (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM marketplace_tasks ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def claim_task(task_id: str, node_id: str, node_name: str) -> Optional[Dict[str, Any]]:
    import time
    with _get_db() as conn:
        conn.execute(
            """UPDATE marketplace_tasks
               SET status = 'claimed', claimed_by = ?, claimed_by_name = ?, claimed_at = ?
               WHERE task_id = ? AND status = 'open'""",
            (node_id, node_name, time.time(), task_id)
        )
        conn.commit()
        return get_task(task_id)


def submit_for_review(task_id: str, result_summary: str) -> Optional[Dict[str, Any]]:
    with _get_db() as conn:
        conn.execute(
            """UPDATE marketplace_tasks
               SET status = 'pending_review', result_summary = ?
               WHERE task_id = ? AND status = 'claimed'""",
            (result_summary, task_id)
        )
        conn.commit()
        return get_task(task_id)


def approve_task(task_id: str, node_payout: float, platform_fee: float) -> Optional[Dict[str, Any]]:
    import time
    with _get_db() as conn:
        conn.execute(
            """UPDATE marketplace_tasks
               SET status = 'completed', completed_at = ?,
                   node_payout = ?, platform_fee = ?
               WHERE task_id = ? AND status = 'pending_review'""",
            (time.time(), node_payout, platform_fee, task_id)
        )
        conn.commit()
        return get_task(task_id)


def reject_task(task_id: str) -> Optional[Dict[str, Any]]:
    with _get_db() as conn:
        conn.execute(
            """UPDATE marketplace_tasks
               SET status = 'open', claimed_by = NULL, claimed_by_name = NULL,
                   claimed_at = NULL, result_summary = NULL, swarmcoder_task_id = NULL
               WHERE task_id = ? AND status = 'pending_review'""",
            (task_id,)
        )
        conn.commit()
        return get_task(task_id)


def complete_task(task_id: str, result_summary: str, node_payout: float, platform_fee: float) -> Optional[Dict[str, Any]]:
    import time
    with _get_db() as conn:
        conn.execute(
            """UPDATE marketplace_tasks
               SET status = 'completed', completed_at = ?, result_summary = ?,
                   node_payout = ?, platform_fee = ?
               WHERE task_id = ? AND status = 'claimed'""",
            (time.time(), result_summary, node_payout, platform_fee, task_id)
        )
        conn.commit()
        return get_task(task_id)


def cancel_task(task_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    with _get_db() as conn:
        conn.execute(
            "UPDATE marketplace_tasks SET status = 'cancelled' WHERE task_id = ? AND user_id = ? AND status = 'open'",
            (task_id, user_id)
        )
        conn.commit()
        return get_task(task_id)


def set_swarmcoder_task_id(task_id: str, sc_task_id: str):
    with _get_db() as conn:
        conn.execute(
            "UPDATE marketplace_tasks SET swarmcoder_task_id = ? WHERE task_id = ?",
            (sc_task_id, task_id)
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------
def add_transaction(tx_id: str, tx_type: str, user_id: str, amount: float,
                    task_id: Optional[str] = None, fee: Optional[float] = None,
                    method: Optional[str] = None) -> Dict[str, Any]:
    import time
    with _get_db() as conn:
        conn.execute(
            """INSERT INTO transactions (tx_id, tx_type, user_id, task_id, amount, fee, method, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (tx_id, tx_type, user_id, task_id, amount, fee, method, time.time())
        )
        conn.commit()
        return get_transaction(tx_id)


def get_transaction(tx_id: str) -> Optional[Dict[str, Any]]:
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM transactions WHERE tx_id = ?", (tx_id,)).fetchone()
        return dict(row) if row else None


def list_transactions(user_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    with _get_db() as conn:
        if user_id:
            rows = conn.execute(
                "SELECT * FROM transactions WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
                (user_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM transactions ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Platform Stats
# ---------------------------------------------------------------------------
def get_platform_stats() -> Dict[str, Any]:
    with _get_db() as conn:
        total_tasks = conn.execute("SELECT COUNT(*) as c FROM marketplace_tasks").fetchone()["c"]
        completed = conn.execute("SELECT COUNT(*) as c FROM marketplace_tasks WHERE status = 'completed'").fetchone()["c"]
        open_bounties = conn.execute("SELECT COUNT(*) as c FROM marketplace_tasks WHERE status = 'open'").fetchone()["c"]
        bounty_vol = conn.execute("SELECT COALESCE(SUM(bounty), 0) as s FROM marketplace_tasks").fetchone()["s"]
        paid_out = conn.execute("SELECT COALESCE(SUM(node_payout), 0) as s FROM marketplace_tasks WHERE status = 'completed'").fetchone()["s"]
        platform_rev = conn.execute("SELECT COALESCE(SUM(platform_fee), 0) as s FROM marketplace_tasks WHERE status = 'completed'").fetchone()["s"]
        recent_tx = list_transactions(limit=20)
        return {
            "platform_revenue": round(platform_rev, 2),
            "total_tasks": total_tasks,
            "completed_tasks": completed,
            "open_bounties": open_bounties,
            "total_bounty_volume": round(bounty_vol, 2),
            "total_paid_to_nodes": round(paid_out, 2),
            "recent_transactions": recent_tx,
        }


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------
def get_leaderboard(limit: int = 10) -> List[Dict[str, Any]]:
    with _get_db() as conn:
        rows = conn.execute(
            """SELECT user_id, total_earned, tasks_completed
               FROM accounts
               ORDER BY total_earned DESC
               LIMIT ?""",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
