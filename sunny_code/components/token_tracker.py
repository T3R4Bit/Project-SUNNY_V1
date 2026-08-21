"""Tracks LLM token usage/spend and enforces the daily/monthly caps from
config.py — the "Token Circuit Breaker" / "Spending Caps" prerequisite
from sunny-vault/docs/architecture/llm-readiness.md, built before any real
LLM feature exists so the safety rail is already tested by the time one does.

Reuses dashboard.py's `token_usage` table in sunny.db (one place records
spend, one place displays it) rather than a parallel store. The schema is
created here too (not just in DashboardDB._init_db) so this module works
correctly even if it's the first thing to touch sunny.db in a given process
(e.g. chat.py, which never constructs a DashboardDB).
"""

import json
import logging
import sqlite3
from datetime import date
from typing import Dict, Tuple

from sunny_code.components.db_connection import closing_transaction
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

# Self-tracked estimate for circuit-breaker purposes, not authoritative
# billing — update if Anthropic pricing changes. $ per 1M tokens.
# Kept in sync with the model table in llm-integration.md.
_PRICING = {
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
    "claude-opus-5": {"input": 5.00, "output": 25.00},
}
# Unrecognized model string -> price as the most expensive known tier, so an
# unmapped model can't silently undercount spend past the cap.
_DEFAULT_PRICING = _PRICING["claude-opus-5"]


def _connect() -> sqlite3.Connection:
    settings = get_settings()
    conn = sqlite3.connect(settings.db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS token_usage (
            date DATE PRIMARY KEY,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_cost REAL,
            by_model TEXT
        )
        """
    )
    return conn


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pricing = _PRICING.get(model, _DEFAULT_PRICING)
    return (prompt_tokens / 1_000_000) * pricing["input"] + (completion_tokens / 1_000_000) * pricing["output"]


def record_usage(model: str, prompt_tokens: int, completion_tokens: int, cost: float) -> None:
    """Add usage to today's rollup row, upserting the by_model breakdown."""
    today = date.today().isoformat()
    with closing_transaction(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT prompt_tokens, completion_tokens, total_cost, by_model FROM token_usage WHERE date = ?",
            (today,),
        ).fetchone()

        if row:
            by_model = json.loads(row["by_model"] or "{}")
            entry = by_model.get(model, {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0})
            entry["prompt_tokens"] += prompt_tokens
            entry["completion_tokens"] += completion_tokens
            entry["cost"] += cost
            by_model[model] = entry
            conn.execute(
                "UPDATE token_usage SET prompt_tokens = ?, completion_tokens = ?, total_cost = ?, by_model = ? WHERE date = ?",
                (
                    row["prompt_tokens"] + prompt_tokens,
                    row["completion_tokens"] + completion_tokens,
                    row["total_cost"] + cost,
                    json.dumps(by_model),
                    today,
                ),
            )
        else:
            by_model = {model: {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "cost": cost}}
            conn.execute(
                "INSERT INTO token_usage (date, prompt_tokens, completion_tokens, total_cost, by_model) VALUES (?, ?, ?, ?, ?)",
                (today, prompt_tokens, completion_tokens, cost, json.dumps(by_model)),
            )
        conn.commit()


def get_today_usage() -> Dict:
    today = date.today().isoformat()
    with closing_transaction(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT prompt_tokens, completion_tokens, total_cost, by_model FROM token_usage WHERE date = ?",
            (today,),
        ).fetchone()

    if not row:
        return {
            "date": today,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost": 0.0,
            "by_model": {},
        }

    return {
        "date": today,
        "prompt_tokens": row["prompt_tokens"] or 0,
        "completion_tokens": row["completion_tokens"] or 0,
        "total_tokens": (row["prompt_tokens"] or 0) + (row["completion_tokens"] or 0),
        "cost": row["total_cost"] or 0.0,
        "by_model": json.loads(row["by_model"] or "{}"),
    }


def get_month_cost() -> float:
    month_prefix = date.today().isoformat()[:7]  # YYYY-MM
    with closing_transaction(_connect()) as conn:
        result = conn.execute(
            "SELECT COALESCE(SUM(total_cost), 0) FROM token_usage WHERE date LIKE ?",
            (f"{month_prefix}-%",),
        ).fetchone()
    return result[0] or 0.0


def check_budget() -> Tuple[bool, str]:
    """(ok, reason). ok=False means: refuse any further LLM calls until the
    day/month rolls over. Checked by llm_client.ask_claude() before every
    call — this is the actual circuit breaker, not just a display number."""
    settings = get_settings()

    today_cost = get_today_usage()["cost"]
    if today_cost >= settings.daily_spend_cap:
        return False, f"daily spend cap reached (${today_cost:.2f} >= ${settings.daily_spend_cap:.2f})"

    month_cost = get_month_cost()
    if month_cost >= settings.monthly_spend_cap:
        return False, f"monthly spend cap reached (${month_cost:.2f} >= ${settings.monthly_spend_cap:.2f})"

    return True, ""
