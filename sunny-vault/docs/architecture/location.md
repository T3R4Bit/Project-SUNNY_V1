---
id: sunny-location
type: feature
status: active
created: 2026-08-19
tags: [feature, weather, location, console]
---

# Location

Where Sunny thinks "here" is, for weather lookups. Set on `/console` (the LOCATION card), not `.env` — a location is runtime state that can change, not a secret, so it saves instantly and takes effect on the very next weather call. No restart.

## Status

Built — `sunny_code/components/location_store.py`, wired into [[weather|sunny_code/components/weather.py]] and the LOCATION card on `/console`.

## Why Not Just an Env Var

`WEATHER_LOCATION` still exists in `.env` and still works — it's the initial fallback if nothing's been saved through the console yet, so an existing setup keeps working untouched. But it's not the primary path anymore, on purpose:

- **Restart-free.** Editing `.env` requires restarting Sunny to take effect (well — technically `get_settings()` re-reads `.env` fresh on every call today, so even that would work live, but that's an implementation detail not a design guarantee). A dedicated store makes "no restart needed" an explicit contract, not an accident of how config happens to be loaded.
- **Not a secret.** `.env` is for things that would be bad to leak (API keys, OAuth client secrets) and gets `chmod 600`'d. A city name isn't that — it doesn't need to live in the same file or carry the same handling.
- **Sets up what's next** (see below) — a single mutable "current location" value is a much smaller step toward per-request location than an env var would be.

## How It Works

- `location_store.get_location()` — checks `location.json` (project root, gitignored) first; falls back to `.env`'s `WEATHER_LOCATION` if that file doesn't exist or is empty/placeholder. Returns `None` if neither is set.
- `location_store.set_location(value)` — writes `location.json`. Immediate effect: the next `weather.get_current()`/`get_tomorrow()` call reads the new value, nothing else to restart or reload.
- `POST /api/weather/location` / `GET /api/weather/location` — the two routes backing the console card (`sunny_code/components/weather_routes.py`).
- `data_sources.is_configured("weather")` requires **both** a real `OPENWEATHERMAP_API_KEY` and `location_store.get_location()` returning something — a key alone can't answer "what's the weather," so it's still honestly reported as "not connected" until both are true.

## Where This Is Headed

Today this is **one static location for the whole assistant** — effectively "home." That's an intentional interim step, not the end state. The plan is for location to become **per-request** instead: reflecting wherever the question is actually being asked from (phone browser geolocation, or a future device's own location) rather than one fixed value tied to the Lenovo.

This ties into the existing backlog item under [[../phases.md#proactive-systems-if-time|Proactive Systems]] — "Location-aware departure nudges" already assumes Sunny knows more than one fixed point. When that gets built, `location_store` is the natural place to grow a per-session or per-device value instead of (or alongside) the single global one it holds today; `get_location()` staying the one call site every consumer goes through is what makes that swap possible without touching `weather.py` or the briefing engine again.

## Files

- `sunny_code/components/location_store.py` — get/set, `.env` fallback
- `sunny_code/components/weather_routes.py` — `/api/weather/location` GET/POST
- `sunny_code/components/weather.py` — reads location via the store, not settings directly
- `sunny_code/components/console_stats.py` — LOCATION card on `/console`
- `sunny_code/components/data_sources.py` — `is_configured("weather")` requires both key and location

## Dependencies

- [[weather|Weather integration]] — the only current consumer
- [[dashboard|Console]] — hosts the input
