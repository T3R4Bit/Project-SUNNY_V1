---
id: sunny-dashboard
type: component
status: retired
created: 2026-08-18
updated: 2026-09-13
tags: [dashboard, monitoring, ui, logs, oauth]
---

# Console — Retired

Sunny's own web console — a tabbed page at `/console` (`sunny_code/components/console.py`): Chat, Stats, Logs, and OAuth Links — was removed 2026-09-13. The standalone **project-dashboard** app (`keaton.dev`, `D:\project-dashboard` / `~/project-dashboard` on `sunshine-m700`) now owns this host's web UI, running in its own Docker container alongside Sunny and Warren. See its own README for what it covers.

Nothing that talked to Sunny's HTTP API was removed — only the page that rendered inside Sunny's own process. `main.py`'s `/` now redirects to `settings.dashboard_url` instead of `/console`.

## What Sunny still exposes for project-dashboard (or anything else) to consume

- `GET /health` — liveness
- `GET /api/dashboard/health`, `/spend/today`, `/spend/month`, `/status`, `/usage/live` — `sunny_code/components/dashboard.py`, unchanged (see [[usage-tracking]])
- `GET /api/calendar/today`, `GET /api/gmail/flagged` — `sunny_code/components/dashboard_data_routes.py`, added for project-dashboard's `/sunny` page
- `GET /api/briefing/*` — the merged morning/evening briefing text
- `GET`/`POST /api/weather/location` — the old LOCATION card's read/write API; no web UI drives it anymore (see [[location]])
- `/auth/google/*`, `/auth/spotify/*` — OAuth login/callback/status/disconnect, unchanged, reached directly on Sunny's own host:port (see [[google-integration]])
- `/legal/*` — required for Google OAuth verification

## What's gone

- The Chat tab (`POST /api/assistant/message`) — talk to Sunny via Discord or `python chat.py` (terminal) instead. There is no browser-based chat interface anymore.
- The Stats tab (`GET /api/stats`, psutil CPU/RAM/disk/temp) — not exposed anywhere now. Would need re-adding to `dashboard.py` or project-dashboard's own Monitors page if wanted again.
- The Logs tab (`GET /api/traces/recent`, `GET /api/traces/stream`) — `sunny_code/components/trace.py` still records every `handle_message()` call to `traces.jsonl` and still supports SSE subscribers (`subscribe()`/`unsubscribe()`), it just has no caller now. `tail -f logs/traces.jsonl` on the host is the only way to watch it live today.
- The OAuth Links tab's clickable cards — the underlying `/auth/google/*` and `/auth/spotify/*` routes are untouched; project-dashboard's `/sunny` page links to them directly instead.

## Dependencies

- [[usage-tracking]] — the separate `/api/dashboard/spend/*` API, still real
- [[google-integration]] — Google OAuth flow, still real, no longer fronted by a console card
- [[networking]] — Tailscale mesh, the access model both Sunny and project-dashboard rely on
