---
id: sunny-google-integration
type: feature
status: active
created: 2026-08-19
tags: [feature, google, oauth, calendar, gmail]
---

# Google Sign-In (OAuth 2.0)

One "Connect Google Account" button on [[dashboard|the console]] that authorizes Sunny to read/write your Calendar and read your Gmail. Code is complete; going live needs a Google Cloud OAuth client (one-time setup, external to this repo) and then a one-time sign-in.

**2026-08-24: the Calendar scope widened from `calendar.readonly` to the full `calendar` scope**, so Sunny can create/delete events, not just read them (see "What This Covers" below). Anyone already connected under the old scope needs to reconnect — Google doesn't retroactively expand a token's scope, and `build_authorization_url()`'s `prompt="consent"` already forces a fresh consent screen on every sign-in, so this is just "click Connect Google Account again," no special re-auth flow needed.

## Status

| Piece | Status |
|-------|--------|
| OAuth flow (login/callback/token storage/refresh) | Built and fixed — `sunny_code/components/google_auth.py`, `google_routes.py`. A real PKCE bug (`invalid_grant: Missing code verifier`) was found and fixed 2026-08-20 — see How It Works |
| Calendar read | Built — `sunny_code/components/google_calendar.py`, wired into [[briefing-engine]] |
| Calendar write (create/delete events) | Built 2026-08-24 — `google_calendar.create_event`/`find_event_by_title`/`delete_event`, natural-language layer in `calendar_parser.py` + `calendar_engine.py`, wired into `assistant.py` alongside every other command engine (tasks/lists/alarms/Spotify) — works from any interface (Discord, console, voice, Pi companion) |
| Gmail read | Built — `sunny_code/components/google_gmail.py`, wired into [[briefing-engine]] |
| Console "Connect Google Account" card | Built — `/console` |
| Styled callback screens (connected/denied/error) | Built 2026-08-20 — was a bare unstyled `<p>` tag before, see How It Works |
| Google Cloud OAuth client (Client ID/Secret) | Created and configured in `.env` |
| HTTPS support (Google requires it for a non-localhost redirect URI) | Built — see HTTPS below |
| Actual sign-in | In progress — the PKCE bug blocked every attempt until it was fixed; not yet confirmed successful end-to-end |

## What This Covers

- `calendar` — full read/write access to every calendar on the account (not just the primary one for reads — see `google_calendar.get_events()`; writes default to `primary`, see `create_event()`)
- `gmail.readonly` — read message headers only, never bodies (unread count, "important"-flagged count, subject lines of the most recent unread)

Plus `openid` + `userinfo.email` just to show which account is connected on the console.

Calendar write is deliberately narrower than "do anything to the calendar": `calendar_engine.py` only exposes create and delete by natural language (e.g. "add dentist appointment to my calendar at 3pm tomorrow", "cancel dentist appointment from my calendar") — no reschedule/move, no recurring events, no attendees/invites. Delete resolves a title to an event via `find_event_by_title()` (case-insensitive substring match across every calendar, soonest upcoming match wins if more than one matches) — there's no confirmation step before deleting, so a substring that matches an unintended event is a real risk worth knowing about.

## What This Does NOT Cover (and why)

Scopes are requested narrowly on purpose — a wider ask both increases what a leaked token could do and (for Gmail specifically) pushes the OAuth consent screen into Google's "restricted scope" verification review. None of the following are wired up:

| Capability | Covered by Google sign-in? | Notes |
|---|---|---|
| **Sending / drafting email** | No | Needs `gmail.send` or `gmail.compose`, not requested. Would unlock the backlog's "Auto-draft email replies" item — add the scope + a `google_gmail.create_draft()` function when that's actually being built. |
| **Rescheduling / moving calendar events, recurring events, invites** | No | Create/delete only (see What This Covers above) — the full `calendar` scope would technically allow more, but nothing calls `events().patch()`/`update()` yet. |
| **Google Drive** | No | Nothing in Sunny's roadmap reads/writes Drive files. Not requested. |
| **Contacts, Photos, Google Tasks** | No | Not referenced anywhere in [[../phases|phases.md]] or [[../BACKLOG]]. Not requested. |
| **Commute / traffic** | **No — not part of Google sign-in at all**, even though it's a Google product. Google Maps Platform (Directions/Routes API) is billed and authenticated per-*project* via a plain API key, not per-*user* OAuth consent. Still needs its own `GOOGLE_MAPS_API_KEY` in `.env` and a small `google_maps.py`/similar — separate piece of work, unrelated to this sign-in flow. |
| **Health / wellness** | No | No Google product is mapped to this in the roadmap. (Google Fit exists and *could* be added later via a `fitness.activity.read` scope, but nothing currently calls for it.) |
| **News, motorsports** | No | Not Google products at all — would need a separate news API, unrelated to this sign-in. |

**Bottom line for the briefing engine**: after connecting, Calendar and Email become real. Weather, commute, health, news, and motorsports are all still open items — see [[briefing-engine]]'s Status table and [[../log/requests|requests.md]] for which ones are actually being asked for in practice.

## Setup (do this once, outside the repo)

1. **Google Cloud Console** → [console.cloud.google.com](https://console.cloud.google.com) → create or select a project.
2. **Enable APIs**: APIs & Services → Library → enable both **Google Calendar API** and **Gmail API**.
3. **OAuth consent screen**: APIs & Services → OAuth consent screen.
   - User type: External.
   - Add the two scopes above (`calendar`, `gmail.readonly`).
   - **Branding**: app logo (`branding/sunny-logo-120.png`, 120×120), home page, privacy policy, and terms of service links — point these at Sunny's own self-hosted pages, not a third-party host (see Legal Pages below for why).
   - **Publishing status: stay in Testing**, and add your own Google account under **Test users**. This is the opposite of what was originally planned here (see below) but is what actually works for a personal single-user app without extra hoops.
4. **Create credentials**: APIs & Services → Credentials → Create Credentials → OAuth client ID.
   - Application type: **Web application**.
   - Authorized redirect URI: `https://<tailscale-hostname>:5443/auth/google/callback` — **must be HTTPS and a real domain name**, not a raw IP (see HTTPS below for why, and for getting the hostname). `http://127.0.0.1:5000/auth/google/callback` also works if testing from the machine running Sunny directly — Google's redirect-URI policy explicitly exempts `localhost`/`127.0.0.1` from both the HTTPS and real-domain requirements.
5. Copy the **Client ID** and **Client Secret** into `.env`:
   ```
   GOOGLE_CLIENT_ID=...
   GOOGLE_CLIENT_SECRET=...
   GOOGLE_OAUTH_REDIRECT_URI=https://<tailscale-hostname>:5443/auth/google/callback
   ```
6. Restart Sunny, open `/console`, and click **Connect Google Account** under the GOOGLE card. Approve the consent screen. The card should flip to `CONNECTED` with your email shown.

### Testing vs. Production — what actually happened here

The original plan (still visible in git history) was "set to In production, unverified-app warning is fine for personal use." That turned out to be wrong in practice: signing in returned `Error 403: access_denied` — Google enforces the Testing/test-users restriction as a hard block, not a warning, for an app that hasn't gone through publishing. The fix that actually worked: **stay in Testing, add yourself as a test user**.

The real tradeoff of staying in Testing: refresh tokens expire every 7 days, so Sunny silently loses Calendar/Gmail access weekly until you reconnect. For a personal single-user tool, that's a reasonable cost to avoid Google's full verification process (which needs a publicly-internet-reachable home/privacy/terms — Tailscale-only hosting doesn't qualify, since Google's reviewers aren't on your tailnet; see Legal Pages below). If the weekly reconnect becomes annoying, formal verification is the way out, but it's a bigger step.

### HTTPS

Google rejects plain-`http://` and raw-IP redirect URIs outright (except for `localhost`/`127.0.0.1`) — the Tailscale IP that used to work here (`100.117.41.53`) no longer passes validation. Fixed with Tailscale's own certificate issuance rather than a third-party CA:

1. One-time, your side: `sudo tailscale set --operator=$USER` (lets the app's user run `tailscale cert` without `sudo`), and enable **HTTPS Certificates** for the tailnet in the [Tailscale admin console](https://login.tailscale.com/admin/dns).
2. `tailscale cert <hostname>.<tailnet>.ts.net` — issues a real Let's Encrypt cert, trusted by ordinary browsers with no `-k`/click-through needed. Find the hostname via `tailscale status --self --json` → `DNSName`.
3. Cert/key land in `certs/` at the project root (gitignored — see `.gitignore`), referenced by `TLS_CERTFILE`/`TLS_KEYFILE` in `.env`.
4. Sunny serves a second uvicorn server on `TLS_PORT` (default `5443`) alongside the existing plain-HTTP port — nothing on the HTTP side changes. See `sunny_code/main.py`'s `start()`.
5. **Renewal**: a weekly cron job (`0 3 * * 0`) re-runs `tailscale cert` in place — Tailscale certs are short-lived (~90 days). The renewed cert only takes effect on the next service restart, though, since uvicorn reads it once at startup — not auto-reloaded.

This required switching production's launch command from `uvicorn sunny_code.main:app` (uvicorn's bare CLI, which can only bind one port) to `python -m sunny_code.main` (runs `SunnyCore.start()`, which can launch multiple `Server` instances). See [[discord-bot]]'s "not yet connected" history for the related bug this same invocation-path issue caused for the Discord bot, fixed the same day.

### Legal Pages

Google's OAuth consent screen branding needs a home page, privacy policy, and terms of service. First attempt used Claude Artifacts — rejected by Google's verification with four issues at once: not registered to the app owner, behind a login page, purpose not explained, and an app-name mismatch. All stemmed from Artifacts requiring a claude.ai login and being hosted on a domain Google can't tie to the app owner.

Fixed by self-hosting three static pages directly from Sunny: `sunny_code/components/legal_pages.py` serves `legal/home.html`, `legal/privacy.html`, `legal/terms.html` (project root) at `/legal/home`, `/legal/privacy`, `/legal/terms`. Written honestly for what this actually is — personal, single-user software, not a company — rather than generic SaaS boilerplate.

**Caveat**: these are reachable at `https://<tailscale-hostname>:5443/legal/...`, which solves "not behind a claude.ai login" but is still only reachable *within the tailnet* — good enough to fill in the consent screen's URL fields for Testing-mode use, but very likely still insufficient for Google's formal verification reviewers, who aren't on your tailnet either. Public reachability (a real registered domain, or a tunnel like Cloudflare Tunnel for just these three pages) would be the next step if formal verification is ever pursued.

## How It Works

- `GET /auth/google/login` — redirects to Google's consent screen (only reachable if `GOOGLE_CLIENT_ID`/`SECRET` are set). Renders a styled "not set up yet" page instead of a bare string if they're missing.
- `GET /auth/google/callback` — Google redirects back here with a `code`; it's exchanged for tokens, the account email is fetched, and both are written to `google_token.json` (project root, gitignored, `chmod 600`). Every outcome (connected, denied, missing params, exchange failure) renders a real styled page — same visual identity as the self-hosted legal pages (see Legal Pages below) — not the bare `<p>` tag this used to be.
- `GET /auth/google/status` — JSON status the console card polls: `client_configured`, `connected`, `email`, `scopes`.
- `POST /auth/google/disconnect` — deletes the local token file (does not revoke access on Google's side — revoke via [myaccount.google.com/permissions](https://myaccount.google.com/permissions) if you want that too).
- `google_auth.get_credentials()` is the one function every other module calls — it loads the stored token, refreshes it if the access token expired, and returns `None` if there's no token or the refresh token was revoked. Every caller (`google_calendar`, `google_gmail`) treats `None` exactly like "not connected," and any live API error is caught and also returns `None` — nothing here can crash a briefing.

### The PKCE bug (fixed 2026-08-20)

Every real sign-in attempt failed with `invalid_grant: Missing code verifier` until this was found. Root cause: `build_authorization_url()` and `handle_callback()` each built their own `google_auth_oauthlib.Flow` object — but `Flow.authorization_url()` is the only place that auto-generates a PKCE `code_verifier`, and it only lives on that specific Flow instance, discarded the moment the function returns. `handle_callback()` runs in an entirely separate HTTP request (the user goes to Google and back in between) with a fresh Flow that never had a verifier at all, so `fetch_token()` sent none — hence "**Missing**," not "mismatched."

Fixed by capturing `flow.code_verifier` alongside the existing `_pending_state` right after `authorization_url()` generates it, and passing that exact value into the callback's `Flow.from_client_config(..., code_verifier=...)`. Both are single in-memory values (matching the existing single-user, single-pending-flow design) — cleared after use.

## Security Notes

- `google_token.json` holds a long-lived refresh token — treated like `.env`: gitignored, `chmod 600` on write. Don't commit it, don't paste its contents anywhere.
- CSRF protection on the OAuth callback is a single in-memory `state` value (`google_auth._pending_state`), and the flow now also relies on a matching single in-memory `code_verifier` (`google_auth._pending_code_verifier`, added with the PKCE fix) — sufficient because Sunny is single-user and this flow is only reachable over Tailscale, not the open internet.
- `certs/tailscale.key` (the TLS private key) is gitignored and `chmod 600`, same posture as `google_token.json` and `.env`.
- Gmail stays read-only; Calendar is now read+write (see the 2026-08-24 note above). A leaked token can read your calendar and email headers, and create/delete calendar events; it still cannot send mail or read message bodies.

## Files

- `sunny_code/components/google_auth.py` — OAuth flow, token storage/refresh, PKCE code_verifier handling
- `sunny_code/components/google_routes.py` — the four `/auth/google/*` routes, styled callback pages
- `sunny_code/components/google_calendar.py` — `get_events(day_offset)`
- `sunny_code/components/google_gmail.py` — `get_summary()`
- `sunny_code/components/data_sources.py` — `is_configured("calendar"|"email")` now checks `google_auth.is_connected()`
- `sunny_code/components/briefing.py` — pulls real Calendar/Gmail data when connected, falls back to the standard "not connected" note otherwise
- `sunny_code/components/console_stats.py` — GOOGLE status card on `/console`
- `sunny_code/components/legal_pages.py` — serves `legal/home.html`, `legal/privacy.html`, `legal/terms.html` for the consent screen's branding links
- `sunny_code/main.py` — `start()`'s dual-server (HTTP + HTTPS) launch, `TLS_CERTFILE`/`TLS_KEYFILE`/`TLS_PORT` in `sunny_code/config.py`

## Dependencies

- [[briefing-engine]] — consumes Calendar + Email data
- [[dashboard]] — hosts the Connect/Disconnect UI
- [[networking]] — the callback URL must be reachable at wherever Sunny is bound; now the Tailscale MagicDNS hostname over HTTPS, not the bare Tailscale IP (see HTTPS above)
