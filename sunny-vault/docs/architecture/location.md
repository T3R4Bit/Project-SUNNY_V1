---
id: sunny-location
type: feature
status: active
created: 2026-08-19
tags: [feature, weather, location, console, gps]
---

# Location

Where Sunny thinks "here" is, for weather lookups. Two sources feed it: a static city (`POST /api/weather/location` — no web UI drives this since Sunny's own console was retired 2026-09-13, see [[dashboard]]) and, as of 2026-08-20, a live GPS fix pushed from the phone via OwnTracks. GPS wins when it's fresh; the static city is the fallback.

## Status

Built — `sunny_code/components/location_store.py`, wired into [[weather|sunny_code/components/weather.py]], `/api/weather/location`, and `sunny_code/components/location_routes.py` for GPS. Setting the static city requires a direct API call (`curl`/similar) today — no browser UI exists for it (see [[dashboard]]'s "What's gone").

## Why Not Just an Env Var

`WEATHER_LOCATION` still exists in `.env` and still works — it's the initial fallback if nothing's been saved via the API yet, so an existing setup keeps working untouched. But it's not the primary path anymore, on purpose:

- **Restart-free.** Editing `.env` requires restarting Sunny to take effect (well — technically `get_settings()` re-reads `.env` fresh on every call today, so even that would work live, but that's an implementation detail not a design guarantee). A dedicated store makes "no restart needed" an explicit contract, not an accident of how config happens to be loaded.
- **Not a secret.** `.env` is for things that would be bad to leak (API keys, OAuth client secrets) and gets `chmod 600`'d. A city name isn't that — it doesn't need to live in the same file or carry the same handling.
- **Sets up what's next** (see below) — a single mutable "current location" value is a much smaller step toward per-request location than an env var would be.

## How It Works

- `location_store.get_location()` — checks `location.json` (project root, gitignored) first; falls back to `.env`'s `WEATHER_LOCATION` if that file doesn't exist or is empty/placeholder. Returns `None` if neither is set.
- `location_store.set_location(value)` — writes `location.json`. Immediate effect: the next `weather.get_current()`/`get_tomorrow()` call reads the new value, nothing else to restart or reload.
- `POST /api/weather/location` / `GET /api/weather/location` — the two routes for reading/setting the static city (`sunny_code/components/weather_routes.py`).
- `data_sources.is_configured("weather")` requires a real `OPENWEATHERMAP_API_KEY` **and either** `location_store.get_location()` (static city) **or** `location_store.get_coordinates()` (a fresh GPS fix) — a key alone can't answer "what's the weather," and a GPS-only setup (no city ever set) must still be honestly reported as connected once a fix exists.
- `location_store.record_gps_fix(lat, lon, tst=None)` — writes `location_gps.json` (project root, gitignored), called by `POST /api/location/owntracks`.
- `location_store.get_coordinates(max_age_minutes=30)` — the last GPS fix, or `None` if there isn't one or it's older than `max_age_minutes`. Sunny never polls the phone; OwnTracks pushes on its own schedule (~30 min by default, or immediately on a "significant" move — see "setup gps"), and staleness is checked entirely on the receiving end.
- `location_store.get_weather_query_params()` — the single decision point every weather call goes through: a fresh GPS fix (`{"lat", "lon"}`) if one exists, else the static city (`{"q": ...}`), else `{}`. `weather.py` merges `appid`/`units` on top and never makes this choice itself.
- `POST /api/location/owntracks` (`sunny_code/components/location_routes.py`) — receives OwnTracks HTTP-mode reports. Optional HTTP Basic Auth via `OWNTRACKS_SHARED_SECRET` (blank = no auth, same trust posture as the rest of this app). Non-`location` message types (`transition`, `card`, `cmd`) are accepted and ignored, not errored — required by the OwnTracks client. Always responds `200 []`.

## Where This Is Headed

This was originally written when location meant **one static city for the whole assistant** — effectively "home" — with the plan being to move to something that reflects wherever the question is actually being asked from. GPS via OwnTracks (2026-08-20) is that: free, self-hosted, no cloud middleman, and it directly answers the BACKLOG ask to stop location defaulting to "ping my phone right now" for every request and instead work off a periodic push with a staleness window.

Still one fixed *device* (the phone), not true per-session/per-device location — fine for a single-user assistant where the phone effectively defines "where the user is." If that ever needs to generalize (a future second device, browser geolocation from wherever a question is asked), `location_store.get_weather_query_params()` staying the one call site every consumer goes through is what makes that swap possible without touching `weather.py` or the briefing engine again. Ties into [[../phases.md#proactive-systems-if-time|Proactive Systems]]' "Location-aware departure nudges," which already assumes Sunny knows more than one fixed point.

## Files

- `sunny_code/components/location_store.py` — static get/set, `.env` fallback, GPS fix storage/staleness, and the combined weather-params decision
- `sunny_code/components/location_routes.py` — `POST /api/location/owntracks`
- `sunny_code/components/weather_routes.py` — `/api/weather/location` GET/POST (static city)
- `sunny_code/components/weather.py` — reads location via the store, not settings directly
- `sunny_code/components/setup_guides.py` — `"setup gps"` guide
- `sunny_code/components/data_sources.py` — `is_configured("weather")` requires a key and (city or GPS)

## Dependencies

- [[weather|Weather integration]] — the only current consumer
- [[dashboard|Console (retired)]] — used to host the input; no replacement UI exists yet
