"""Configuration management using pydantic-settings."""

from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


def looks_configured(value: Optional[str]) -> bool:
    """True if `value` looks like a real secret, not empty and not a
    leftover placeholder from the .env template (see run.sh — every
    placeholder there, e.g. '...' or 'sk-ant-...', ends in '...'). No real
    API key/token/client-id/client-secret ends in three literal dots, so
    this is a safe way to tell "never filled in" from "actually set"."""
    v = (value or "").strip()
    return bool(v) and not v.endswith("...")


class Settings(BaseSettings):
    """Application settings from environment or .env file."""

    # App
    app_name: str = "Project SUNNY"
    app_env: str = "development"  # development, production
    debug: bool = True

    # Paths
    project_root: Path = Path(__file__).parent.parent
    logs_dir: Path = project_root / "logs"
    db_path: Path = project_root / "sunny.db"
    config_dir: Path = project_root / "config"
    google_token_path: Path = project_root / "google_token.json"

    # Network
    tailscale_ip: str = "100.117.41.53"  # Lenovo brain
    api_port: int = 5000
    api_host: str = "127.0.0.1"  # Local dev, will bind to tailscale_ip on brain

    # The standalone project-dashboard app (keaton.dev) running alongside
    # Sunny on the same host -- Sunny's own web console (console.py) was
    # retired 2026-09-13 in favor of it. Used only to point users at it from
    # Discord/log messages; Sunny itself never calls into it.
    dashboard_url: str = "http://100.117.41.53:8088"

    # APIs
    claude_api_key: str = ""
    openweathermap_api_key: str = ""
    # OpenWeatherMap needs a place, not just a key — "City,State,CountryCode",
    # e.g. "Detroit,MI,US" (state code only applies to US cities).
    weather_location: str = ""

    # OwnTracks GPS reporting (see sunny_code/components/location_routes.py)
    # — optional HTTP Basic Auth on the receiving endpoint. Blank means
    # auth is skipped entirely, matching this app's existing single-user,
    # Tailscale-only trust posture.
    owntracks_shared_secret: str = ""

    # Google Sign-In (OAuth 2.0) — powers Calendar + Gmail. See
    # sunny-vault/docs/architecture/google-integration.md for the Google
    # Cloud Console setup steps required before this works.
    google_client_id: str = ""
    google_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://127.0.0.1:5000/auth/google/callback"

    # Spotify (OAuth 2.0, PKCE) — powers voice playback control. See
    # sunny-vault/docs/architecture/spotify-integration.md for the Spotify
    # Developer Dashboard setup steps required before this works. Requires
    # Spotify Premium — the Web API's playback-control endpoints reject
    # Free-tier accounts.
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_oauth_redirect_uri: str = "http://127.0.0.1:5000/auth/spotify/callback"
    spotify_token_path: Path = project_root / "spotify_token.json"

    # Discord bot — DISCORD_CHAT_CHANNEL_ID is the one required channel the bot
    # reads commands from (tasks/lists/alarms/server-admin). DISCORD_TASKS_
    # CHANNEL_ID is a separate, optional, read-only home for the pinned task
    # dashboard — falls back to the chat channel if unset, so a bare chat
    # channel alone reproduces the old single-channel behavior. The remaining
    # three are optional *output* channels for specific things — the bot never
    # reads commands from any of them. Any left unset (0) means that output
    # keeps going to the chat channel instead — see
    # sunny-vault/docs/architecture/discord-bot.md.
    discord_bot_token: str = ""
    discord_chat_channel_id: int = 0
    discord_tasks_channel_id: int = 0
    discord_briefings_channel_id: int = 0
    discord_warnings_channel_id: int = 0
    discord_task_updates_channel_id: int = 0
    discord_health_channel_id: int = 0
    # Claude API usage dashboard + spend-cap alerts -- unset falls back to
    # the health channel, then the chat channel, same layered fallback as
    # every other output-only channel. Previously always shared the health
    # channel; this exists to split it back out into its own channel.
    discord_usage_channel_id: int = 0
    # Class-deadline reminders (class_deadlines.py's T-2/T-0 pings) --
    # unset falls back to the chat channel, same as the other output-only
    # channels above.
    discord_reminders_channel_id: int = 0
    # The voice channel Sunny stays connected to persistently (see
    # voice_session.py) -- unlike the output-only channels above, unset
    # means voice presence just doesn't start, not "falls back to chat."
    discord_voice_channel_id: int = 0

    @field_validator(
        "discord_chat_channel_id",
        "discord_tasks_channel_id",
        "discord_briefings_channel_id",
        "discord_warnings_channel_id",
        "discord_task_updates_channel_id",
        "discord_health_channel_id",
        "discord_usage_channel_id",
        "discord_reminders_channel_id",
        "discord_voice_channel_id",
        mode="before",
    )
    @classmethod
    def _coerce_channel_id(cls, v):
        """A blank value or a leftover '...' placeholder from the .env template
        (see run.sh) means "not set," same as omitting the line entirely —
        not a crash. Settings() is built from a hand-edited .env (an external
        boundary), so this is real input validation, not a hypothetical.

        No logging here on purpose — get_settings() constructs a fresh
        Settings() on every call (by design, so a live .env/location edit
        needs no restart), so this validator runs far more often than
        "someone changed something." key_status.startup_summary() already
        reports this once, cleanly, instead of flooding the log."""
        if v in (None, ""):
            return 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    # Spending caps
    daily_spend_cap: float = 20.0  # USD per day
    monthly_spend_cap: float = 100.0  # USD per month

    # TLS (optional) — some external providers require HTTPS on the redirect/
    # callback URI (e.g. Google OAuth won't accept a plain-http non-localhost
    # URI). Empty means "not configured": Sunny serves plain HTTP only on
    # api_port, same as always. See sunny-vault/docs/architecture/
    # google-integration.md for how these get populated (a Tailscale-issued
    # cert, not a manually-managed one).
    tls_certfile: str = ""
    tls_keyfile: str = ""
    tls_port: int = 5443

    # Local wall-clock timezone — used by the weekly health check's Sunday
    # 4am trigger (see sunny_code/components/health_check.py). Bound once
    # at startup, not live-reloaded like most settings here — changing this
    # needs a restart.
    local_timezone: str = "America/New_York"

    # Optional, user-maintained API key expiry dates (YYYY-MM-DD), checked
    # by the weekly health check. Blank means "skip this key's check" — none
    # of these providers expose real expiration dates via API, so this is
    # opt-in and only as accurate as you keep it.
    claude_api_key_expires: str = ""
    openweathermap_api_key_expires: str = ""
    discord_bot_token_expires: str = ""
    google_client_secret_expires: str = ""

    # Piper TTS (see sunny_code/components/tts.py) — free, fully local, no
    # API cost. Model downloads automatically to piper_voices_dir on first
    # use if not already present (~60MB, one time). All of these take effect
    # on the very next /speak call, no restart needed — same uncached-by-
    # design pattern as get_settings() itself.
    piper_voice: str = "en_US-lessac-medium"
    piper_voices_dir: Path = project_root / "piper_voices"

    # Optional tuning knobs (blank = use the voice model's own baked-in
    # defaults). See sunny-vault/docs/architecture/tts-piper.md's "Tuning
    # Piper's Voice" section for what each does and where to start.
    piper_length_scale: Optional[float] = None
    piper_noise_scale: Optional[float] = None
    piper_noise_w_scale: Optional[float] = None
    piper_speaker_id: Optional[int] = None

    @field_validator(
        "piper_length_scale", "piper_noise_scale", "piper_noise_w_scale",
        mode="before",
    )
    @classmethod
    def _coerce_optional_float(cls, v):
        """Same "blank/placeholder means unset" contract as
        _coerce_channel_id above, for optional floats instead of required
        ints — blank means "use Piper's own default for this voice", not
        a crash."""
        if v in (None, ""):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    @field_validator("piper_speaker_id", mode="before")
    @classmethod
    def _coerce_optional_int(cls, v):
        if v in (None, ""):
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    # Vosk STT (see sunny_code/components/stt.py) — free, fully local, no
    # API cost. Model downloads automatically to vosk_model_dir on first
    # use if not already present. vosk_model_name picks a specific named
    # model (bigger vocabulary/better accuracy than the tiny default —
    # see the real model list at alphacephei.com/vosk/models, verified
    # 2026-08-20, not guessed); blank falls back to vosk_lang's small
    # model (the original default, ~39MB vs. lgraph's ~125MB).
    #
    # Reverted from "vosk-model-en-us-0.22-lgraph" back to blank
    # (small model), 2026-08-21: root-caused via faulthandler catching a
    # live native abort mid-crash -- a Kaldi assertion deep inside
    # LatticeIncrementalDecoderTpl::ProcessNonemitting()
    # ("Assertion failed: (queue_.empty())"), specifically inside
    # FinalResult()'s own internal flush logic, not anything reachable
    # or fixable from this codebase (it's inside libvosk.so's compiled
    # Kaldi internals, no source available to patch). This is the
    # "incremental lattice decoder" -- exactly the graph structure the
    # "-lgraph" model name refers to. The small model ran for hours
    # earlier this same session with zero native crashes; every crash
    # chased all evening (several real, independently-fixed bugs along
    # the way, all worth keeping) only started after this specific model
    # was switched to. Revisit if a non-"-lgraph" bigger model
    # (vosk-model-en-us-0.22) turns out not to share this decoder path,
    # or if upstream Vosk/Kaldi fixes this assertion.
    vosk_model_dir: Path = project_root / "vosk_models"
    vosk_lang: str = "en-us"
    vosk_model_name: str = ""

    # LLM freeform-conversation tuning (see briefing.py's custom_briefing()
    # fallback and sunny_code/components/llm_client.py's ask_claude()) —
    # the system prompt itself lives in sunny-vault/docs/instructions/
    # general-chat.md (hand-editable, no restart needed, see
    # instructions.py); these three control everything ask_claude() takes
    # besides the prompt text. All optional, all take effect on the very
    # next call, no restart needed — same uncached-by-design pattern as
    # every other setting here.
    llm_chat_model: str = "haiku"  # "haiku" (fast/cheap), "sonnet"
    # (more capable, slower/pricier), or "opus" (rarely worth it here) --
    # see llm_client.MODELS for the full name->model-id mapping.
    llm_chat_max_tokens: int = 300  # a hard cap on reply length. Kept
    # well below ask_claude()'s own 1024 default since these replies are
    # meant to be short and often spoken aloud (see general-chat.md's own
    # "keep it to a few sentences" instruction) -- this is the backstop
    # if a reply tries to run long anyway.
    llm_chat_temperature: Optional[float] = None  # 0.0 = deterministic,
    # 1.0 = Anthropic's own default, higher = more varied/less literal.
    # None leaves it unset entirely (the API's own default applies).

    @field_validator("llm_chat_temperature", mode="before")
    @classmethod
    def _coerce_optional_temperature(cls, v):
        if v in (None, ""):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json or text

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def get_settings() -> Settings:
    """Build a fresh Settings from the current .env — deliberately not cached,
    so a live edit (location, an API key) takes effect on the very next call
    with no restart. Called often; keep this cheap and side-effect-free."""
    return Settings()
