---
id: sunny-google-integration
type: feature
status: active
created: 2026-08-19
tags: [feature, google, oauth, calendar, gmail]
---

# Google Sign-In (OAuth 2.0)

One "Connect Google Account" button on [[dashboard|the console]] that authorizes Sunny to read your Calendar and Gmail. Code is complete; going live needs a Google Cloud OAuth client (one-time setup, external to this repo) and then a one-time sign-in.

## Status

| Piece | Status |
|-------|--------|
| OAuth flow (login/callback/token storage/refresh) | ✅ Built — `sunny_code/components/google_auth.py`, `google_routes.py` |
| Calendar read | ✅ Built — `sunny_code/components/google_calendar.py`, wired into [[briefing-engine]] |
| Gmail read | ✅ Built — `sunny_code/components/google_gmail.py`, wired into [[briefing-engine]] |
| Console "Connect Google Account" card | ✅ Built — `/console` |
| Google Cloud OAuth client (Client ID/Secret) | ⚠️ **You still need to create this** — see Setup below |
| Actual sign-in | ⚠️ Not done until you click Connect on `/console` |

## What This Covers

Two scopes, both read-only:

- `calendar.readonly` — read events off the primary calendar (today's schedule, tomorrow's preview)
- `gmail.readonly` — read message headers only, never bodies (unread count, "important"-flagged count, subject lines of the most recent unread)

Plus `openid` + `userinfo.email` just to show which account is connected on the console.

## What This Does NOT Cover (and why)

Scopes are requested narrowly on purpose — a wider ask both increases what a leaked token could do and (for Gmail/Calendar specifically) pushes the OAuth consent screen into Google's "restricted scope" verification review. None of the following are wired up:

| Capability | Covered by Google sign-in? | Notes |
|---|---|---|
| **Sending / drafting email** | ❌ No | Needs `gmail.send` or `gmail.compose`, not requested. Would unlock the backlog's "Auto-draft email replies" item — add the scope + a `google_gmail.create_draft()` function when that's actually being built. |
| **Writing/creating calendar events** | ❌ No | Needs the full `calendar` scope (this only has `calendar.readonly`). Would unlock "Proactive calendar updates (detect changes, update automatically)" from the backlog. |
| **Google Drive** | ❌ No | Nothing in Sunny's roadmap reads/writes Drive files. Not requested. |
| **Contacts, Photos, Google Tasks** | ❌ No | Not referenced anywhere in [[../phases|phases.md]] or [[../BACKLOG]]. Not requested. |
| **Commute / traffic** | ❌ **No — not part of Google sign-in at all**, even though it's a Google product. Google Maps Platform (Directions/Routes API) is billed and authenticated per-*project* via a plain API key, not per-*user* OAuth consent. Still needs its own `GOOGLE_MAPS_API_KEY` in `.env` and a small `google_maps.py`/similar — separate piece of work, unrelated to this sign-in flow. |
| **Health / wellness** | ❌ No | No Google product is mapped to this in the roadmap. (Google Fit exists and *could* be added later via a `fitness.activity.read` scope, but nothing currently calls for it.) |
| **News, motorsports** | ❌ No | Not Google products at all — would need a separate news API, unrelated to this sign-in. |

**Bottom line for the briefing engine**: after connecting, Calendar and Email become real. Weather, commute, health, news, and motorsports are all still open items — see [[briefing-engine]]'s Status table and [[../log/requests|requests.md]] for which ones are actually being asked for in practice.

## Setup (do this once, outside the repo)

1. **Google Cloud Console** → [console.cloud.google.com](https://console.cloud.google.com) → create or select a project.
2. **Enable APIs**: APIs & Services → Library → enable both **Google Calendar API** and **Gmail API**.
3. **OAuth consent screen**: APIs & Services → OAuth consent screen.
   - User type: External.
   - Add your own Google account as a **test user**.
   - Add the two scopes above (`calendar.readonly`, `gmail.readonly`).
   - **Publishing status**: set to **In production**, not "Testing." Testing-mode refresh tokens expire after 7 days, which means Sunny would silently lose Calendar/Gmail access every week. Production mode without full verification still works fine for personal/single-user use — you'll just see an "unverified app" warning on the consent screen the first time you sign in, which is expected; click "Advanced" → "Go to Project SUNNY (unsafe)" to proceed. This is normal for a self-hosted personal tool and does not mean anything is actually wrong.
4. **Create credentials**: APIs & Services → Credentials → Create Credentials → OAuth client ID.
   - Application type: **Web application**.
   - Authorized redirect URI: `http://100.117.41.53:5000/auth/google/callback` (the Lenovo's Tailscale address — match `TAILSCALE_IP`/`API_PORT` in `.env`). Add `http://127.0.0.1:5000/auth/google/callback` too if you'll ever test from the machine running Sunny directly.
5. Copy the **Client ID** and **Client Secret** into `.env`:
   ```
   GOOGLE_CLIENT_ID=...
   GOOGLE_CLIENT_SECRET=...
   GOOGLE_OAUTH_REDIRECT_URI=http://100.117.41.53:5000/auth/google/callback
   ```
6. Restart Sunny, open `/console`, and click **Connect Google Account** under the GOOGLE card. Approve the consent screen. The card should flip to `CONNECTED` with your email shown.

## How It Works

- `GET /auth/google/login` — redirects to Google's consent screen (only reachable if `GOOGLE_CLIENT_ID`/`SECRET` are set).
- `GET /auth/google/callback` — Google redirects back here with a `code`; it's exchanged for tokens, the account email is fetched, and both are written to `google_token.json` (project root, gitignored, `chmod 600`).
- `GET /auth/google/status` — JSON status the console card polls: `client_configured`, `connected`, `email`, `scopes`.
- `POST /auth/google/disconnect` — deletes the local token file (does not revoke access on Google's side — revoke via [myaccount.google.com/permissions](https://myaccount.google.com/permissions) if you want that too).
- `google_auth.get_credentials()` is the one function every other module calls — it loads the stored token, refreshes it if the access token expired, and returns `None` if there's no token or the refresh token was revoked. Every caller (`google_calendar`, `google_gmail`) treats `None` exactly like "not connected," and any live API error is caught and also returns `None` — nothing here can crash a briefing.

## Security Notes

- `google_token.json` holds a long-lived refresh token — treated like `.env`: gitignored, `chmod 600` on write. Don't commit it, don't paste its contents anywhere.
- CSRF protection on the OAuth callback is a single in-memory `state` value (`google_auth._pending_state`) — sufficient because Sunny is single-user and this flow is only reachable over Tailscale, not the open internet.
- Scopes are read-only. A leaked token can read your calendar and email headers; it cannot send mail, create events, or read message bodies.

## Files

- `sunny_code/components/google_auth.py` — OAuth flow, token storage/refresh
- `sunny_code/components/google_routes.py` — the four `/auth/google/*` routes
- `sunny_code/components/google_calendar.py` — `get_events(day_offset)`
- `sunny_code/components/google_gmail.py` — `get_summary()`
- `sunny_code/components/data_sources.py` — `is_configured("calendar"|"email")` now checks `google_auth.is_connected()`
- `sunny_code/components/briefing.py` — pulls real Calendar/Gmail data when connected, falls back to the standard "not connected" note otherwise
- `sunny_code/components/console_stats.py` — GOOGLE status card on `/console`

## Dependencies

- [[briefing-engine]] — consumes Calendar + Email data
- [[dashboard]] — hosts the Connect/Disconnect UI
- [[networking]] — the callback URL must be reachable at wherever Sunny is bound (Tailscale IP)
