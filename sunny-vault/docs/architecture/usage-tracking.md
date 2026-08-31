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
| Persistent usage dashboard in Discord (append-only, every 6h) | Built (2026-08-23, cadence changed 2026-08-27) |
| Daily spend/expiry alert ping | Built (2026-08-23) |
| Real Anthropic-reported usage/rate-limit data (not just self-tracked cost) | Built (2026-08-24) |

## How Cost Is Calculated

`token_tracker.py` self-calculates cost from a local `$/1M token` price table (`_PRICING`) — **not** authoritative Anthropic billing. `record_usage()` upserts a per-day, per-model row in `sunny.db`'s `token_usage` table after every `ask_claude()`/`ask_claude_stream()` attempt. An unrecognized model ID prices at the *most expensive* known tier rather than the cheapest, so an unmapped model can't quietly slip under the spend cap. If Anthropic's real rates change, `_PRICING` has to be updated by hand — this is a deliberate, known gap (see BACKLOG.md's "real Claude usage/limits from Anthropic's API" item).

## The `/usage` Chart

`usage_chart.render_usage_chart_png(days=30)` — a single-series matplotlib bar chart (daily cost, last N days), rendered dark-surface-first since it's always viewed as a Discord image attachment on Discord's own dark theme. Token count is real but a different scale from cost, so it's shown as text in the embed description rather than a second y-axis. Runs headless (`matplotlib.use("Agg")`), never raises on empty data (renders real zero-bars instead of erroring).

## Persistent Dashboard + Alerts

Both live in `discord_bot.py`, posting to `discord_usage_channel_id` — a dedicated channel if one's configured, otherwise falling back to `discord_health_channel_id` (the weekly health check's channel — see [[health-check]]), then `chat_channel_id`:

- **`refresh_usage_dashboard()`** — a loop (`usage_refresh_loop`, runs immediately then every 6 hours as of 2026-08-27, slowed from hourly) posts the chart as a **brand-new** embed each time with `**$X.XX** today · **$Y.YY** this month (cap $Z/day, $W/month)`. As of 2026-08-27 this is append-only — no delete, no edit, no pinned-message tracking (the earlier delete-and-resend-via-footer-marker approach was dropped, so the channel accumulates one post per refresh instead of always showing exactly one current message).
- **`check_usage_alerts()`** — pings the same channel once per calendar day (tracked by date, not a one-shot flag, so a new day's crossing still alerts even if yesterday's already did) when spend crosses 70% of the daily/monthly self-imposed cap, or a tracked API key is expiring within a week — the same expiry check the weekly health report does, surfaced immediately here instead of waiting for Sunday.

## Real Anthropic Rate-Limit Data (2026-08-24)

Everything above is this app's own self-tracked cost estimate. Separately, `token_tracker.get_latest_rate_limits()` holds Anthropic's own real-time numbers — `anthropic-ratelimit-{requests,tokens,input-tokens,output-tokens}-{limit,remaining,reset}` — straight from the response headers on the most recent Claude call:

- `llm_client.py`'s non-streaming path calls `client.messages.with_raw_response.create(...)` instead of a plain `.create()`, then `.parse()`s the same `Message` object back out — everything else about that function is unchanged. The streaming path (`ask_claude_stream`) reads `stream.response.headers` right after entering the stream context, before any chunks are consumed.
- **In-memory only, current-window snapshot** — not persisted to `sunny.db`, not logged historically, resets on every restart. These headers describe "how much is left in the current rate window," not a fact worth keeping after the next call overwrites it.
- Surfaced via `GET /api/dashboard/usage/live`, an extra line on Discord's `/usage` chart when data exists, and a new cross-interface "what's my usage" voice/text intent (`assistant.py`) that answers with both the self-tracked spend and (when available) the real remaining-tokens number — works identically from console, Discord, and the Pi companion, since it's routed through the same `handle_message()` everything else uses. This is distinct from `sunny-companion/BUILD_PLAN.md`'s still-open item to wire Anthropic's separate **Admin API** (`cost_report`, org-level, needs its own Admin API key) into a visual dashboard payload on the Pi's screen — that's a different, richer feature this doesn't replace.

## History: the #health channel consolidation (2026-08-23), then split back out (2026-08-25)

This dashboard originally lived in its own dedicated channel (`DISCORD_USAGE_CHANNEL_ID`). Moved into `#health` the same day as the weekly health check's own embed rework, for one consistent place to look for "is anything wrong or costing more than expected" — same embed style (bold key figures), same channel. `DISCORD_USAGE_CHANNEL_ID` was removed as a setting at that point; both read `discord_health_channel_id`.

Re-added 2026-08-25 by request — `discord_usage_channel_id` is back, sitting ahead of `discord_health_channel_id` in the fallback chain rather than replacing it, so an existing setup that never sets the new variable keeps behaving exactly as it did during the consolidation (usage posts land in `#health`, same as before). Setting it just splits usage back into its own channel without touching the health report's channel at all.

## Files

- `sunny_code/components/token_tracker.py` — recording, cost calculation, `check_budget()` circuit breaker, `get_today_usage()`/`get_month_cost()`/`get_daily_costs()`
- `sunny_code/components/usage_chart.py` — chart rendering
- `sunny_code/components/discord_bot.py` — `refresh_usage_dashboard()`, `check_usage_alerts()`, `usage_refresh_loop`
- `sunny_code/components/dashboard.py` — `token_usage` table schema, `/api/dashboard/spend/*` and `/usage/live` endpoints
- `sunny_code/components/llm_client.py` — `with_raw_response`/`stream.response.headers` capture
- `sunny_code/components/assistant.py` — the cross-interface "what's my usage" intent
- `sunny_code/config.py` — `daily_spend_cap`, `monthly_spend_cap`, `discord_usage_channel_id`, `discord_health_channel_id`

## Dependencies

- [[llm-integration]] — the circuit breaker this visibility layer sits on top of
- [[health-check]] — shares a channel and an embed style; the weekly report's own key-expiry check is what `check_usage_alerts()` reuses for its daily version
- [[discord-bot]] — hosts both the chart command and the persistent dashboard

## Implementation Checklist

- [x] Cost self-tracking with a conservative unmapped-model fallback
- [x] Hard spend caps enforced in-app (daily + monthly)
- [x] Dashboard API endpoints (today/month)
- [x] `/usage [days]` chart command
- [x] Persistent dashboard, append-only, refreshed every 6 hours (2026-08-27, slowed from hourly delete-and-resend)
- [x] Daily 70%-of-cap / key-expiring-soon alert, deduped per calendar day
- [x] Consolidated into `#health` alongside the weekly health check (2026-08-23), then given back its own optional channel — `DISCORD_USAGE_CHANNEL_ID` (2026-08-25), falling back to `#health` then chat if unset
- [x] Real Anthropic-reported usage/rate-limit data from API response headers (not just self-tracked cost) — `GET /api/dashboard/usage/live`, `/usage`'s extra line, and a cross-interface "what's my usage" intent
- [ ] Hard cap set at the Anthropic account level (external, manual, separate from the in-app cap) — see [[llm-readiness]]
