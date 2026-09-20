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
from datetime import date, timedelta
from typing import Dict, List, Tuple

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


_pooled_conn: sqlite3.Connection | None = None


def _connect() -> sqlite3.Connection:
    """Long-lived module-level connection, reused across calls instead of
    reopening sunny.db every time — this module is single-process-only
    (only the main server touches sunny.db's token_usage table; chat.py,
    the one other process that runs this codebase, never does), so unlike
    scheduled_db.py's scheduled.db there's no cross-process lock-contention
    concern here. Schema creation is idempotent (IF NOT EXISTS) so it only
    needs to run once, on first connect, not on every call."""
    global _pooled_conn
    if _pooled_conn is None:
        settings = get_settings()
        conn = sqlite3.connect(settings.db_path)
        conn.row_factory = sqlite3.Row
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
        _pooled_conn = conn
    return _pooled_conn


def close() -> None:
    """Release the pooled connection. Call on app shutdown."""
    global _pooled_conn
    if _pooled_conn is not None:
        _pooled_conn.close()
        _pooled_conn = None


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pricing = _PRICING.get(model, _DEFAULT_PRICING)
    return (prompt_tokens / 1_000_000) * pricing["input"] + (completion_tokens / 1_000_000) * pricing["output"]


def record_usage(model: str, prompt_tokens: int, completion_tokens: int, cost: float) -> None:
    """Add usage to today's rollup row, upserting the by_model breakdown."""
    today = date.today().isoformat()
    conn = _connect()
    with conn:
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
    conn = _connect()
    with conn:
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


def get_daily_costs(days: int = 30) -> List[Dict]:
    """One row per day for the last `days` days (oldest first), zero-filled
    for any day with no recorded usage -- built for usage_chart.py, which
    needs a real value (even if 0.0) for every day on the x-axis, not just
    the days a row happens to exist for. Each row: date (YYYY-MM-DD), cost,
    total_tokens."""
    today = date.today()
    start = (today - timedelta(days=days - 1)).isoformat()
    conn = _connect()
    with conn:
        rows = conn.execute(
            "SELECT date, prompt_tokens, completion_tokens, total_cost FROM token_usage WHERE date >= ? ORDER BY date",
            (start,),
        ).fetchall()

    by_date = {
        row["date"]: {
            "cost": row["total_cost"] or 0.0,
            "total_tokens": (row["prompt_tokens"] or 0) + (row["completion_tokens"] or 0),
        }
        for row in rows
    }

    result = []
    for i in range(days):
        day = (today - timedelta(days=days - 1 - i)).isoformat()
        entry = by_date.get(day, {"cost": 0.0, "total_tokens": 0})
        result.append({"date": day, "cost": entry["cost"], "total_tokens": entry["total_tokens"]})
    return result


def get_month_cost() -> float:
    month_prefix = date.today().isoformat()[:7]  # YYYY-MM
    conn = _connect()
    with conn:
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


# Anthropic's own real-time usage/rate-limit numbers, from the response
# headers on every Messages API call — distinct from everything above,
# which is this app's own self-tracked cost estimate. Deliberately just an
# in-memory snapshot of the most recent call, not persisted to sunny.db or
# logged historically: these headers describe Anthropic's *current* rate
# window (e.g. "here's how many tokens you have left in this minute"), not
# a fact about a point in time worth keeping around after the next call
# overwrites it. Reset to empty on every process restart, same as any other
# "as of the last call" snapshot in this app.
_RATE_LIMIT_HEADER_KEYS = (
    "anthropic-ratelimit-requests-limit",
    "anthropic-ratelimit-requests-remaining",
    "anthropic-ratelimit-requests-reset",
    "anthropic-ratelimit-tokens-limit",
    "anthropic-ratelimit-tokens-remaining",
    "anthropic-ratelimit-tokens-reset",
    "anthropic-ratelimit-input-tokens-limit",
    "anthropic-ratelimit-input-tokens-remaining",
    "anthropic-ratelimit-input-tokens-reset",
    "anthropic-ratelimit-output-tokens-limit",
    "anthropic-ratelimit-output-tokens-remaining",
    "anthropic-ratelimit-output-tokens-reset",
)
_latest_rate_limits: Dict[str, str] = {}


def record_rate_limit_headers(headers) -> None:
    """Called after every real Anthropic API response (both the
    non-streaming and streaming paths in llm_client.py) with the response's
    headers -- anything httpx.Headers-like (a .get(key) lookup is all this
    needs). Silently keeps only the subset of headers this app recognizes;
    an Anthropic response missing one (older API version, a header rename)
    just leaves that key out rather than erroring."""
    global _latest_rate_limits
    found = {key: headers.get(key) for key in _RATE_LIMIT_HEADER_KEYS if headers.get(key) is not None}
    if found:
        _latest_rate_limits = found


def get_latest_rate_limits() -> Dict[str, str]:
    """A copy of the most recent call's rate-limit headers, or {} if no
    real Anthropic call has happened yet this process. Values are strings
    (as Anthropic sends them) -- e.g. a *-reset header is an ISO 8601
    timestamp, not a number of seconds; left as-is rather than parsed,
    since nothing here does arithmetic on it, only displays it."""
    return dict(_latest_rate_limits)
