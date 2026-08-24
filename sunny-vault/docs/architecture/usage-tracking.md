---
id: sunny-usage-tracking
type: component
status: active
created: 2026-08-24
tags: [usage, spend, dashboard, discord, component]
---

# Usage & Spend Tracking

Claude is the one clearly-paid API in this app (OpenWeatherMap/Google Calendar/Gmail are free-tier, Discord is free) — this covers how its usage/cost is tracked, capped, and surfaced. See [[llm-integration]] for the circuit breaker itself; this doc is about visibility on top of it.

## Status

| Piece | Status |
|-------|--------|
| Usage recording (`token_usage` table, `sunny.db`) | Built — `token_tracker.py` |
| Hard-cap circuit breaker | Built — see [[llm-integration]] |
| `GET /api/dashboard/spend/today` / `/spend/month` | Built |
| `/usage [days]` Discord chart command | Built — `usage_chart.py` |
| Persistent hourly-updated usage dashboard in Discord | Built (2026-08-23) |
| Daily spend/expiry alert ping | Built (2026-08-23) |
| Real Anthropic-reported usage/rate-limit data (not just self-tracked cost) | Not built — see BACKLOG.md |

## How Cost Is Calculated

`token_tracker.py` self-calculates cost from a local `$/1M token` price table (`_PRICING`) — **not** authoritative Anthropic billing. `record_usage()` upserts a per-day, per-model row in `sunny.db`'s `token_usage` table after every `ask_claude()`/`ask_claude_stream()` attempt. An unrecognized model ID prices at the *most expensive* known tier rather than the cheapest, so an unmapped model can't quietly slip under the spend cap. If Anthropic's real rates change, `_PRICING` has to be updated by hand — this is a deliberate, known gap (see BACKLOG.md's "real Claude usage/limits from Anthropic's API" item).

## The `/usage` Chart

`usage_chart.render_usage_chart_png(days=30)` — a single-series matplotlib bar chart (daily cost, last N days), rendered dark-surface-first since it's always viewed as a Discord image attachment on Discord's own dark theme. Token count is real but a different scale from cost, so it's shown as text in the embed description rather than a second y-axis. Runs headless (`matplotlib.use("Agg")`), never raises on empty data (renders real zero-bars instead of erroring).

## Persistent Dashboard + Alerts (in `#health`)

Both live in `discord_bot.py`, in the same Discord channel as the weekly health check (`discord_health_channel_id` — see [[health-check]]):

- **`refresh_usage_dashboard()`** — an hourly loop (`usage_refresh_loop`, runs immediately then every hour) posts the chart as an embed with `**$X.XX** today · **$Y.YY** this month (cap $Z/day, $W/month)`. Unlike the task dashboard's edit-in-place pattern, this is **delete-and-resend** — Discord's embed image cache can hold a stale thumbnail through an attachment-replacing edit, so a fresh message guarantees a fresh chart image every time. Recognizes its own prior pinned message across restarts via a footer marker (`USAGE_MARKER`), same technique as the task dashboard's zero-width-space marker.
- **`check_usage_alerts()`** — pings the same channel once per calendar day (tracked by date, not a one-shot flag, so a new day's crossing still alerts even if yesterday's already did) when spend crosses 70% of the daily/monthly self-imposed cap, or a tracked API key is expiring within a week — the same expiry check the weekly health report does, surfaced immediately here instead of waiting for Sunday.

Both fall back to `chat_channel_id` if `discord_health_channel_id` isn't set, same pattern as the health check's own posting.

## History: the #health channel consolidation (2026-08-23)

This dashboard originally lived in its own dedicated channel (`DISCORD_USAGE_CHANNEL_ID`). Moved into `#health` the same day as the weekly health check's own embed rework, for one consistent place to look for "is anything wrong or costing more than expected" — same embed style (bold key figures), same channel. `DISCORD_USAGE_CHANNEL_ID` no longer exists as a setting; both now read `discord_health_channel_id`.

## Files

- `sunny_code/components/token_tracker.py` — recording, cost calculation, `check_budget()` circuit breaker, `get_today_usage()`/`get_month_cost()`/`get_daily_costs()`
- `sunny_code/components/usage_chart.py` — chart rendering
- `sunny_code/components/discord_bot.py` — `refresh_usage_dashboard()`, `check_usage_alerts()`, `usage_refresh_loop`
- `sunny_code/components/dashboard.py` — `token_usage` table schema, `/api/dashboard/spend/*` endpoints
- `sunny_code/config.py` — `daily_spend_cap`, `monthly_spend_cap`, `discord_health_channel_id`

## Dependencies

- [[llm-integration]] — the circuit breaker this visibility layer sits on top of
- [[health-check]] — shares a channel and an embed style; the weekly report's own key-expiry check is what `check_usage_alerts()` reuses for its daily version
- [[discord-bot]] — hosts both the chart command and the persistent dashboard

## Implementation Checklist

- [x] Cost self-tracking with a conservative unmapped-model fallback
- [x] Hard spend caps enforced in-app (daily + monthly)
- [x] Dashboard API endpoints (today/month)
- [x] `/usage [days]` chart command
- [x] Persistent hourly-updated dashboard, delete-and-resend to dodge Discord's image cache
- [x] Daily 70%-of-cap / key-expiring-soon alert, deduped per calendar day
- [x] Consolidated into `#health` alongside the weekly health check
- [ ] Real Anthropic-reported usage/rate-limit data from API response headers (not just self-tracked cost) — see BACKLOG.md
- [ ] Hard cap set at the Anthropic account level (external, manual, separate from the in-app cap) — see [[llm-readiness]]
