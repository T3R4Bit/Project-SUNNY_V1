---
id: sunny-spotify-integration
type: feature
status: active
created: 2026-08-23
tags: [feature, spotify, oauth, voice, playback]
---

# Spotify Voice Control (OAuth 2.0)

Lets Sunny control Spotify playback the way Siri does — "play [song]", "pause", "skip", "what's playing" — spoken through the same voice pipeline (Discord's persistent voice presence, the Pi companion) or typed through the console/Discord chat. One "Connect Spotify Account" button on [[dashboard|the console]], same shape as [[google-integration|Google Sign-In]].

## What This Covers

Transport controls plus catalog search-and-play by name:

- `play <song/artist>` — searches Spotify's catalog and starts the first match
- `pause` / `resume`
- `skip` (next track) / `previous song`
- `volume up` / `volume down` / `set volume to <N>`
- `what's playing`

Scopes: `user-modify-playback-state`, `user-read-playback-state`, `user-read-currently-playing` — playback control and read-only "what's active" state. Nothing about library, playlists, saved tracks, or listening history.

## What This Does NOT Cover (and why)

- **Device targeting** — deliberate. Every command acts on whatever device Spotify itself considers "active" (`/v1/me/player/*` with no `device_id`), exactly like the Spotify app or Siri. Sunny has no concept of "this speaker" anywhere in its voice pipeline (see [[voice-io]]) — adding one would need new config (a stored `SPOTIFY_DEVICE_ID`) and was left out on purpose to keep this a straight mirror of how Siri actually behaves.
- **Queue management, playlist creation/editing, library browsing** — not requested, would need additional scopes (`playlist-modify-public/private`, `user-library-modify`) beyond the narrow playback-only ask here.
- **Spotify Premium is required.** The Web API's playback-control endpoints (`play`/`pause`/`next`/`previous`/`volume`) return `403 PREMIUM_REQUIRED` for Free-tier accounts — Sunny surfaces this as a plain spoken message rather than a raw API error.

## Setup (do this once, outside the repo)

1. **Spotify Developer Dashboard** → [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) → log in → Create app.
2. **Redirect URI**: Spotify requires HTTPS for every redirect URI *except* the literal loopback `http://127.0.0.1:<port>/...` — a Tailscale IP/hostname does **not** qualify as loopback, so a real-machine setup needs the same Tailscale-issued HTTPS cert Google's integration uses (see [[google-integration]]'s HTTPS section — `certs/tailscale.crt`/`tailscale.key`, `TLS_PORT` default `5443`). Add `https://<tailscale-hostname>.<tailnet>.ts.net:5443/auth/spotify/callback` (find the hostname via `tailscale status --self --json` → `DNSName`), or `http://127.0.0.1:5000/auth/spotify/callback` only if testing directly on the machine running Sunny.
3. Copy the **Client ID** and **Client Secret** into `.env`:
   ```
   SPOTIFY_CLIENT_ID=...
   SPOTIFY_CLIENT_SECRET=...
   SPOTIFY_OAUTH_REDIRECT_URI=https://<your-tailscale-hostname>.<tailnet>.ts.net:5443/auth/spotify/callback
   ```
4. Restart Sunny, open `/console`, and click **Connect Spotify Account** under the SPOTIFY card. Approve the consent screen. The card should flip to `CONNECTED` with your account name shown.
5. Open Spotify somewhere (phone, desktop, speaker) before trying a voice command — with nothing active, every command replies "Open Spotify on a device first."

## How It Works

- `GET /auth/spotify/login` — redirects to Spotify's consent screen (only reachable if `SPOTIFY_CLIENT_ID`/`SECRET` are set).
- `GET /auth/spotify/callback` — Spotify redirects back here with a `code`; it's exchanged for tokens (PKCE, no Google-auth-library equivalent — hand-rolled with `requests`), the account name is fetched via `/v1/me`, both written to `spotify_token.json` (project root, gitignored, `chmod 600`).
- `GET /auth/spotify/status` — JSON status the console card polls: `client_configured`, `connected`, `username`, `scopes`.
- `POST /auth/spotify/disconnect` — deletes the local token file (does not revoke access on Spotify's side).
- `spotify_auth.get_credentials()` — loads the stored access token, refreshing via the refresh-token grant if expired (Spotify access tokens are short-lived, ~1hr; refresh tokens are long-lived and don't expire like Google's Testing-mode 7-day tokens do). Returns `None` if never connected or the refresh token was revoked; every caller (`spotify_engine`) treats that exactly like "not connected."
- `spotify_engine.SpotifyEngine.try_execute()` — parses the command (`spotify_parser.SpotifyCommandParser`), calls the matching `/v1/me/player/*` endpoint, and translates Spotify's error responses (`404 NO_ACTIVE_DEVICE`, `403 PREMIUM_REQUIRED`) into plain spoken messages instead of raw API errors.

## Security Notes

- `spotify_token.json` holds a long-lived refresh token — treated like `.env` and `google_token.json`: gitignored, `chmod 600` on write.
- CSRF protection on the OAuth callback is a single in-memory `state` value plus a matching single in-memory PKCE `code_verifier` (`spotify_auth._pending_state`/`_pending_code_verifier`) — same posture as Google's fix, sufficient because Sunny is single-user and this flow is only reachable over Tailscale.
- Scopes are playback-only. A leaked token can control what's playing; it cannot read or modify your library, playlists, or listening history.

## Files

- `sunny_code/components/spotify_auth.py` — OAuth flow (hand-rolled PKCE), token storage/refresh
- `sunny_code/components/spotify_routes.py` — the four `/auth/spotify/*` routes, styled callback pages
- `sunny_code/components/spotify_engine.py` — `try_execute()`, the actual Web API playback calls
- `sunny_code/components/spotify_parser.py` — regex command parser (`SpotifyCommandParser`)
- `sunny_code/components/assistant.py` — routes matched Spotify commands before falling through to tasks/briefing
- `sunny_code/components/console_stats.py` — SPOTIFY status card on `/console`
- `sunny_code/main.py` — `SpotifyEngine` instantiation, router registration, threaded into every `handle_message()` caller

## Dependencies

- [[dashboard]] — hosts the Connect/Disconnect UI
- [[voice-io]] — the voice pipeline that actually delivers spoken Spotify commands to `handle_message()`
