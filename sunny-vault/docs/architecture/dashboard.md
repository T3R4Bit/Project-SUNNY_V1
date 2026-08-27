---
id: sunny-dashboard
type: component
status: active
created: 2026-08-18
updated: 2026-08-27
tags: [dashboard, monitoring, ui, logs, oauth]
---

# Console — Local Web UI

Sunny's one web surface: a tabbed page at `/console` (`sunny_code/components/console.py`). Bound to Tailscale interface only — `0.0.0.0:5000` (reachable both locally and over Tailscale; security comes from Tailscale being the only network that can route to the box, not from interface binding), no authentication of its own.

This replaces the previous `console_stats.py` + `chatbot_ui.py` split, and replaces this doc's earlier 7-panel target design (Spend/Health/Host Resources/Clock Battery/Tailscale/Needs Attention/Recent Activity), which was never built — see git history if that design is ever worth revisiting.

## Overview

**Framework**: FastAPI, single router in `console.py`
**Port**: 5000 (`http://<tailscale-ip>:5000/console`)
**Access**: From phone or laptop anywhere via Tailscale mesh
**Authentication**: None (Tailscale itself is the security boundary)
**`/` and `/chatbot`**: redirect to `/console`

## The Four Tabs

### Chat

Free-text chat with Sunny — `POST /api/assistant/message`, routed through `sunny_code.components.assistant.handle_message()`, the same entry point Discord and the Pi companion use. History persists per-browser in `localStorage`.

### Stats

Live system resources — `GET /api/stats` (psutil: CPU/RAM/disk/temp/network), Tailscale IP/hostname, and the weather location editor (`GET`/`POST /api/weather/location`, unchanged from before).

### Logs

Real-time execution-trace viewer. Every `handle_message()` call — web chat, Discord, Pi companion — is recorded by `sunny_code/components/trace.py`:

- **Columns**: timestamp, input, routing decision (which branch of `handle_message()` handled it, e.g. `tasks_engine`, `spotify_engine`, `briefing`), path taken (a more specific sub-label, e.g. `morning`, `qa`), result, errors.
- **Color-coding**: a trace is success (green) unless `handle_message()` raised an exception, in which case it's failure (red) with the exception recorded as the error. A branch returning a normal "couldn't do that" reply is not treated as a failure — only real exceptions are.
- **Click a row** to expand full detail: source (web/discord/pi), session id, duration, full input/result/error.
- **Storage**: JSON-lines at `<logs_dir>/traces.jsonl`, rotated the same way `logging_config.py` rotates `sunny.log` (10MB/10 backups).
- **Live updates**: Server-Sent Events (`GET /api/traces/stream`) — one in-process pub/sub, works because the whole app is a single process (see `main.py`'s `SunnyCore.start()`). `GET /api/traces/recent` backfills the table on page load / SSE reconnect.
- **Instrumentation**: routing branches call `trace.mark_route(route, path)` via a `contextvars.ContextVar` right before returning — doesn't change any branch's control flow, just tags which path fired. An untagged branch reports `"unclassified"` rather than breaking anything.

### OAuth Links

Quick-connect cards for every OAuth integration, each surfacing its existing `/status`, `/login`, `/disconnect` endpoints (unchanged — see [[google-integration]] and `spotify_routes.py`):

- **Google** — `/auth/google/*` — Calendar + Gmail (read-only)
- **Spotify** — `/auth/spotify/*` — playback control

Adding a third provider is a one-entry addition to `OAUTH_PROVIDERS` in `console.py`'s script, provided it follows the same `login`/`callback`/`status`/`disconnect` route shape.

## What's Explicitly Not Here

`sunny_code/components/dashboard.py` (`/api/dashboard/*`) is a separate SQLite-backed JSON API — `spend/today`, `spend/month`, `usage/live` are real and documented in [[usage-tracking]]; `metrics/record`/`metrics/latest`/`health` are unused today. It isn't rendered anywhere on `/console` — spend visibility lives in Discord (`/usage` chart, the persistent `#health` dashboard). It's a distinct, untouched surface, not part of this page.

Hardware panels from the old target design (Clock battery, Tailscale mesh device list, host uptime/thermal) were never built and aren't part of the current console — there's no clock-device or tailscale-mesh-status integration in the codebase to back them.

## Access from Phone

1. Phone joined to the Tailscale mesh.
2. Navigate to `http://<tailscale-ip>:5000/console` (or just `/`, which redirects there).
3. All four tabs work identically to the desktop view (responsive layout).

## Dependencies

- [[usage-tracking]] — the separate `/api/dashboard/spend/*` API this page does *not* render
- [[google-integration]] — Google OAuth flow behind the OAuth Links tab's Google card
- [[networking]] — Tailscale mesh, the access model this page relies on
- `sunny_code/components/assistant.py` — `handle_message()`, the traced entry point
- `sunny_code/components/trace.py` — trace storage + SSE broadcast
- psutil (Python) — Stats tab's system metrics
