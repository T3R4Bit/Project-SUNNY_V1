"""Discord bot — task/list/alarm/reminder commands, server administration
(channels/roles), and a live-updating task dashboard.

Task/list/alarm/briefing commands use the exact same routing as the web
console and terminal chat (sunny_code.components.assistant.handle_message),
so behavior is identical across interfaces. Server-admin commands
(create/delete channels and roles) are Discord-only and checked separately
(see sunny_code.components.server_admin_parser) — they need a live
discord.Guild, which only exists here, so they can't route through that
shared, interface-agnostic handler.

Two distinct channel roles, deliberately separate (not the same channel):
- DISCORD_CHAT_CHANNEL_ID (required) — the one channel commands are read
  from, including server-admin commands. Messages elsewhere are ignored.
- DISCORD_TASKS_CHANNEL_ID (optional, falls back to the chat channel) — a
  read-only home for the pinned task dashboard. Nothing is ever read from
  here; it's purely a display surface, so it stays uncluttered by chat.

Also the only real delivery mechanism for alarms/reminders today: there's no
clock/speaker hardware yet, so "sounding" an alarm means posting a message in
the chat channel when it's due (see the scheduled-items loop below).

Real slash commands: /speak (Piper TTS, one-shot text-to-audio attachment),
/category, /services, /service, /vacation, /usage. No /join/leave anymore —
live voice-channel conversation (stt.py/voice_session.py — see
sunny-vault/docs/architecture/voice-join.md) is a persistent presence now,
not a per-use command; see voice_presence_loop below. Everything else here
is plain-text via handle_message(). Slash commands registered via a
discord.app_commands.CommandTree bound directly to this bare discord.Client
(no commands.Bot needed), synced to this bot's one guild in on_ready.

Setup steps: see sunny-vault/docs/architecture/discord-bot.md
"""

import asyncio
import io
import logging
from datetime import datetime
from typing import Literal, Optional, Tuple

import discord
from discord.ext import tasks

from sunny_code.components import (
    build_info, category_store, class_deadlines, pdf_text, service_registry, storm_mode, token_tracker, tts,
    usage_chart, voice_session,
)
from sunny_code.components.console import get_tailscale_ip
from sunny_code.components.assistant import handle_message, is_briefing_trigger
from sunny_code.components.briefing import BriefingEngine
from sunny_code.components.crash_check import check_previous_crash
from sunny_code.components import google_auth
from sunny_code.components.key_status import expiring_within, missing_api_keys, startup_summary
from sunny_code.components.lists_engine import ListEngine
from sunny_code.components.project_engine import ProjectEngine
from sunny_code.components.scheduled_engine import ScheduledEngine
from sunny_code.components.server_admin_parser import ServerAdminParser
from sunny_code.components.spotify_engine import SpotifyEngine
from sunny_code.components.calendar_engine import CalendarEngine
from sunny_code.components.tasks_engine import TaskEngine
from sunny_code.components.time_parse import next_occurrence
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

DASHBOARD_MARKER = "​" # zero-width space appended to the dashboard message so a
# restarted bot can recognize its own pinned message and start editing it again
HEALTH_MARKER = "⁠" # word joiner (U+2060) -- deliberately a *different*
# invisible character than DASHBOARD_MARKER, so pin-rediscovery for one
# can never accidentally match the other's message if both channels ever
# end up configured to the same channel.
USAGE_ALERT_THRESHOLD = 0.7 # fraction of daily_spend_cap/monthly_spend_cap
# that triggers a ping -- "70%" per the backlog item this implements
_STORM_MODE_TRIGGERS = (
    "storm mode", "activate storm mode", "start storm mode", "turn on storm mode", "enable storm mode",
    "can we start storm mode", "can you start storm mode",
    "can we activate storm mode", "can you activate storm mode",
    "let's start storm mode", "lets start storm mode",
)
_STORM_MODE_STOP_TRIGGERS = (
    "stop storm mode", "end storm mode", "turn off storm mode", "disable storm mode", "cancel storm mode",
    "can we stop storm mode", "can you stop storm mode",
    "can we end storm mode", "can you end storm mode",
    "let's stop storm mode", "lets stop storm mode",
)
_STORM_MODE_STATUS_TRIGGERS = ("storm mode status", "is storm mode on", "storm mode on?")
_WIZARD_CANCEL_WORDS = ("cancel", "nevermind", "never mind", "stop", "skip", "forget it")
MAX_MESSAGE_LENGTH = 1900 # Discord's real limit is 2000; leave headroom
SCHEDULED_CHECK_INTERVAL_SECONDS = 30
VOICE_PRESENCE_INTERVAL_SECONDS = 30 # how often to reconcile actual voice
# connection state against desired (service enabled + channel configured) --
# same cadence as scheduled_check_loop, snappy enough that a reconnect
# after a drop/crash doesn't leave Sunny absent for long
MORNING_PREP_LOOKAHEAD_SECONDS = 5 * 60 # how far ahead of an alarm to
# prewarm the morning briefing -- "5min max" per the backlog item this implements
CLASS_REMINDERS_CHECK_INTERVAL_SECONDS = 3 * 60 * 60 # class_deadlines.check_and_notify()
# is date-only (not time-of-day) comparison and self-guards against
# double-sending, so a few-times-a-day cadence is plenty -- no need for
# scheduled_check_loop's 30s granularity here
SPEAK_MAX_CHARS = 1000 # practical cap on synthesis time/file size, well under
# Discord's own 6000-char slash-command string option limit


def _chunk_message(text: str, limit: int = MAX_MESSAGE_LENGTH):
    """Split text into Discord-safe chunks, preferring newline boundaries."""
    if len(text) <= limit:
        return [text]

    chunks = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


def _find_channel(guild: discord.Guild, name: str):
    name = name.lower().lstrip("#")
    return discord.utils.find(lambda c: c.name.lower() == name, guild.channels)


_PDF_CONTENT_TYPES = ("application/pdf",)


async def _resolve_message_text(message: discord.Message) -> Tuple[str, Optional[str]]:
    """Combines message.content with text extracted from a PDF attachment
    -- e.g. a syllabus sent as a file instead of pasted (see
    class_setup_engine.py, the first real consumer of this; before this
    existed, a PDF-only message had empty .content and was silently
    treated as blank everywhere, which is exactly what made "set up my
    classes" quietly do nothing for a real user who attached syllabus
    PDFs instead of pasting text).

    Returns (effective_text, error). error is a user-facing message to
    send instead of proceeding -- more than one PDF in one message (no
    safe way to guess which class each belongs to), or the one PDF
    attached couldn't be read at all. effective_text is message.content
    unchanged when there's no PDF attachment and no error."""
    pdfs = [
        a for a in message.attachments
        if a.content_type in _PDF_CONTENT_TYPES or a.filename.lower().endswith(".pdf")
    ]
    if not pdfs:
        return message.content, None
    if len(pdfs) > 1:
        return message.content, (
            f"That's {len(pdfs)} PDFs in one message — I can only take one syllabus at a time. "
            "Send each one in its own message and I'll ask about the next after each."
        )

    try:
        pdf_bytes = await pdfs[0].read()
    except discord.HTTPException as e:
        logger.warning(f"Failed to download PDF attachment {pdfs[0].filename}: {e}")
        return message.content, f'Couldn\'t download "{pdfs[0].filename}" — try attaching it again.'

    extracted = pdf_text.extract_text(pdf_bytes)
    if extracted is None:
        return message.content, (
            f'Couldn\'t read any text out of "{pdfs[0].filename}" — it might be a scanned image '
            "with no real text layer, password-protected, or not a real PDF. Try pasting the text directly instead."
        )

    combined = f"{message.content}\n\n{extracted}".strip() if message.content.strip() else extracted
    return combined, None


def build_dashboard_embed(dashboard_data: dict, project_names: list) -> discord.Embed:
    """Renders TaskEngine.get_dashboard_data() as a Discord embed — one
    field per active category, plus a Projects field listing whatever
    project folders exist on disk (populated by the "new project" flow;
    project_names is a plain directory listing the caller supplies, not
    something this function reads itself, so it's testable without a real
    vault on disk). Module-level (not a closure in create_discord_bot())
    so this can be unit-tested directly with synthetic data."""
    stats = dashboard_data["stats"]

    due_soon = dashboard_data["due_soon"]
    description = f"{len(due_soon)} task{'s' if len(due_soon) != 1 else ''} due this week" if due_soon else None
    embed = discord.Embed(title="Your Tasks", description=description, color=discord.Color.blurple())

    for tag, tag_tasks in dashboard_data["categories"]:
        lines = []
        for task in tag_tasks[:5]:
            due_str = f" (due {task['due_date']})" if task["due_date"] else ""
            lines.append(f"{task['title']}{due_str}")
        if len(tag_tasks) > 5:
            lines.append(f"...and {len(tag_tasks) - 5} more")
        embed.add_field(name=f"{tag} ({len(tag_tasks)})", value="\n".join(lines) or "(none)", inline=False)

    embed.add_field(name="Projects", value="\n".join(project_names) if project_names else "(none yet)", inline=False)

    embed.set_footer(
        text=f"Open: {stats['open']} | In Progress: {stats['in_progress']} | Done: {stats['done']}{DASHBOARD_MARKER}"
    )
    return embed


def build_briefing_embed(text: str) -> discord.Embed:
    """Renders a morning/evening briefing (see BriefingTemplates in
    briefing.py -- the same plain-text block the web console and voice
    pipeline read as-is) as a Discord embed instead of a wall of plain
    text, matching the visual language every other embed in this module
    uses (build_dashboard_embed above, /usage, the weekly health report).
    Title comes from the template's own "=== ... ===" banner line; the
    rest becomes the embed body. Only called when
    assistant.is_briefing_trigger() confirmed the response really is a
    briefing -- see on_message below."""
    title, _, body = text.strip("\n").partition("\n\n")
    title = title.strip("= ").title() if title.startswith("===") else "Briefing"
    color = discord.Color.gold() if "morning" in title.lower() else discord.Color.dark_blue()
    return discord.Embed(title=title, description=body.strip()[:4096], color=color)


def _find_role(guild: discord.Guild, name: str):
    name = name.lower()
    return discord.utils.find(lambda r: r.name.lower() == name, guild.roles)


async def _execute_server_admin(action: str, data: dict, guild: discord.Guild, chat_channel_id: int) -> str:
    """Run one server-admin command against a live guild. Never raises —
    Discord API errors (missing permission, role-hierarchy limits, etc.)
    become a plain-text reply, same fail-quietly contract as the rest of
    the app. Deletions execute immediately, no confirmation step — same
    trust model as task/list deletion elsewhere in this app."""
    try:
        if action == "list_channels":
            names = ", ".join(f"#{c.name}" for c in guild.text_channels) or "(none)"
            return f"CHANNELS\n{names}"

        if action == "create_channel":
            channel = await guild.create_text_channel(data["name"])
            return f"Created channel #{channel.name}"

        if action == "delete_channel":
            channel = _find_channel(guild, data["name"])
            if channel is None:
                return f"No channel named \"{data['name']}\" found"
            if channel.id == chat_channel_id:
                return "Can't delete the channel I'm listening in — that would strand me with no way to talk to you here."
            await channel.delete()
            return f"Deleted channel #{channel.name}"

        if action == "list_roles":
            names = ", ".join(r.name for r in guild.roles if not r.is_default()) or "(none)"
            return f"ROLES\n{names}"

        if action == "create_role":
            role = await guild.create_role(name=data["name"])
            return f"Created role \"{role.name}\""

        if action == "delete_role":
            role = _find_role(guild, data["name"])
            if role is None:
                return f"No role named \"{data['name']}\" found"
            if role.is_default():
                return "Can't delete @everyone — Discord doesn't allow it."
            await role.delete()
            return f"Deleted role \"{role.name}\""

        if action in ("assign_role", "remove_role"):
            role = _find_role(guild, data["role_name"])
            if role is None:
                return f"No role named \"{data['role_name']}\" found"
            member = guild.get_member(data["user_id"]) or await guild.fetch_member(data["user_id"])
            if action == "assign_role":
                await member.add_roles(role)
                return f"Gave {member.display_name} the \"{role.name}\" role"
            await member.remove_roles(role)
            return f"Removed the \"{role.name}\" role from {member.display_name}"

    except discord.Forbidden:
        return "I don't have permission to do that — check my role has Manage Channels/Manage Roles, and (for roles) sits above the role being changed."
    except discord.NotFound:
        return "That no longer exists — someone may have already removed it."
    except discord.HTTPException as e:
        return f"Discord rejected that: {e}"

    return f"Unrecognized server-admin action: {action}"


def create_discord_bot(
    tasks_engine: TaskEngine,
    briefing_engine: BriefingEngine,
    list_engine: ListEngine,
    scheduled_engine: ScheduledEngine,
    project_engine: ProjectEngine,
    spotify_engine: SpotifyEngine,
    calendar_engine: CalendarEngine,
    chat_channel_id: int,
    dashboard_channel_id: int = 0,
    briefings_channel_id: int = 0,
    warnings_channel_id: int = 0,
    task_updates_channel_id: int = 0,
    health_channel_id: int = 0,
    usage_channel_id: int = 0,
    reminders_channel_id: int = 0,
    voice_channel_id: int = 0,
) -> discord.Client:
    """Build (but don't start) the Discord client. chat_channel_id is the only
    channel commands are read from. dashboard_channel_id is where the pinned
    task dashboard lives — falls back to chat_channel_id if unset, so leaving
    it unconfigured reproduces the old single-channel behavior exactly. The
    remaining optional *_channel_id args are output-only destinations, except
    voice_channel_id — the voice channel Sunny stays persistently connected
    to (see voice_presence_loop below) when unset, no voice presence starts
    at all — see sunny-vault/docs/architecture/discord-bot.md."""
    dashboard_channel_id = dashboard_channel_id or chat_channel_id

    intents = discord.Intents.default()
    intents.message_content = True # required to read command text, not just embeds/mentions

    client = discord.Client(intents=intents)
    tree = discord.app_commands.CommandTree(client)
    client.tree = tree # exposed for introspection/testing, and for future slash commands to extend
    state = {
        "dashboard_message_id": None,
        "health_message_id": None,
        "usage_alert_date": None,
        "storm_wizard": None,
        "morning_prep_alarm_id": None,
        "posted_key_status": False,
        "commands_synced": False,
        "posted_crash_notice": False,
    }

    @tree.command(name="speak", description="Speak this text out loud (Piper TTS, posted as an audio attachment)")
    async def speak_command(
        interaction: discord.Interaction,
        text: str,
        delivery: Literal["default", "warning", "reminder", "casual"] = "default",
    ):
        """The bot's first slash command — everything else is plain-text via
        handle_message(). Restricted to the chat channel, same as every
        other command this bot has, and deferred since Piper's first call
        (model load, or a one-time download) can take longer than Discord's
        3-second initial-response window."""
        if interaction.channel_id != chat_channel_id:
            await interaction.response.send_message(
                "Use /speak in the chat channel.", ephemeral=True
            )
            return
        if len(text) > SPEAK_MAX_CHARS:
            await interaction.response.send_message(
                f"That's {len(text)} characters — keep it under {SPEAK_MAX_CHARS}.", ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        message_type = None if delivery == "default" else delivery
        try:
            wav_bytes = await asyncio.to_thread(tts.synthesize_wav_bytes, text, message_type)
        except Exception as e:
            logger.error(f"/speak synthesis failed: {e}", exc_info=True)
            await interaction.followup.send("Couldn't synthesize that — check the logs.", ephemeral=True)
            return
        await interaction.followup.send(
            file=discord.File(io.BytesIO(wav_bytes), filename="speech.wav"), ephemeral=True
        )

    @tree.command(name="classsetup", description="Start the class-setup wizard (paste a syllabus per class)")
    async def class_setup_command(interaction: discord.Interaction):
        """Kicks off the same multi-step wizard "set up my classes" starts
        in plain text — see assistant.py's _CLASS_SETUP_TRIGGERS/
        _advance_class_setup_wizard. Public, not ephemeral, unlike /speak:
        this starts a real back-and-forth (semester name, dates, then a
        syllabus per class) that continues as ordinary messages in the
        channel, so the whole thread needs to stay visible, not just this
        first prompt. session_id matches on_message()'s own convention
        exactly, so a plain-text reply right after this command continues
        the same wizard the same way a typed "set up my classes" would."""
        if interaction.channel_id != chat_channel_id:
            await interaction.response.send_message(
                "Use /classsetup in the chat channel.", ephemeral=True
            )
            return
        session_id = f"discord:{interaction.channel_id}:{interaction.user.id}"
        response = await handle_message(
            "set up my classes", tasks_engine, briefing_engine, list_engine, scheduled_engine,
            project_engine, spotify_engine, calendar_engine, session_id=session_id,
        )
        await interaction.response.send_message(response)

    async def _notify_voice_crash(text: str):
        # The voice pipeline runs in an isolated worker process specifically
        # so a native crash there can't take the rest of the bot down with
        # it — this is how that still becomes visible in Discord right
        # away, same channel as every other warning. See
        # voice_session.py/voice_worker.py. voice_presence_loop below
        # reconnects automatically on its next tick; this is purely a
        # notice, not something that needs a manual response.
        await _post_to(warnings_channel_id, text, fallback_channel_id=chat_channel_id)

    @tree.command(name="category", description="Add or remove a task category")
    async def category_command(interaction: discord.Interaction, action: Literal["add", "remove"], name: str):
        if interaction.channel_id != chat_channel_id:
            await interaction.response.send_message(
                "Use /category in the chat channel.", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        if action == "add":
            _, message = category_store.add_category(name)
        else:
            _, message = category_store.remove_category(name)
        await interaction.followup.send(message, ephemeral=True)
        await refresh_dashboard()

    @tree.command(name="version", description="Show the commit Sunny is currently running")
    async def version_command(interaction: discord.Interaction):
        if interaction.channel_id != chat_channel_id:
            await interaction.response.send_message(
                "Use /version in the chat channel.", ephemeral=True
            )
            return
        await interaction.response.send_message(f"Build {build_info.get_build_version()}", ephemeral=True)

    @tree.command(name="ip", description="Show Sunny's current Tailscale IP and a console link")
    async def ip_command(interaction: discord.Interaction):
        if interaction.channel_id != chat_channel_id:
            await interaction.response.send_message(
                "Use /ip in the chat channel.", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        # get_tailscale_ip() shells out to the `tailscale` CLI (up to a 2s
        # timeout) -- run off the event loop so a slow/hung call doesn't
        # stall the bot's message handling, same reasoning as /speak and
        # /usage below.
        tailscale_ip = await asyncio.to_thread(get_tailscale_ip)
        if tailscale_ip is None:
            await interaction.followup.send(
                "Couldn't get a Tailscale IP — is `tailscaled` running on the host?", ephemeral=True
            )
            return
        await interaction.followup.send(
            f"Tailscale IP: `{tailscale_ip}`\nConsole: http://{tailscale_ip}:5000/console", ephemeral=True
        )

    @tree.command(name="services", description="Show on/off + autostart status for every background service")
    async def services_command(interaction: discord.Interaction):
        if interaction.channel_id != chat_channel_id:
            await interaction.response.send_message(
                "Use /services in the chat channel.", ephemeral=True
            )
            return
        lines = service_registry.status_lines()
        lines.append(f"vacation_mode: {'on' if service_registry.is_vacation_mode() else 'off'}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @tree.command(name="service", description="Enable/disable a service, or toggle whether it autostarts on boot")
    async def service_command(
        interaction: discord.Interaction,
        name: Literal[
            "dashboard_refresh", "scheduled_check", "usage_refresh", "health_check", "morning_prep",
            "voice_join", "rules_engine", "class_reminders",
        ],
        action: Literal["enable", "disable", "autostart_on", "autostart_off"],
    ):
        if interaction.channel_id != chat_channel_id:
            await interaction.response.send_message(
                "Use /service in the chat channel.", ephemeral=True
            )
            return
        if action == "enable":
            _, message = service_registry.set_enabled(name, True)
        elif action == "disable":
            _, message = service_registry.set_enabled(name, False)
        elif action == "autostart_on":
            _, message = service_registry.set_autostart(name, True)
        else:
            _, message = service_registry.set_autostart(name, False)
        await interaction.response.send_message(message, ephemeral=True)

    @tree.command(name="vacation", description="Pause morning-prep and morning/evening nudges until turned back off")
    async def vacation_command(interaction: discord.Interaction, mode: Literal["on", "off"]):
        if interaction.channel_id != chat_channel_id:
            await interaction.response.send_message(
                "Use /vacation in the chat channel.", ephemeral=True
            )
            return
        _, message = service_registry.set_vacation_mode(mode == "on")
        await interaction.response.send_message(message, ephemeral=True)

    @tree.command(name="usage", description="Chart of Claude API cost over the last N days (the one paid API here)")
    async def usage_command(interaction: discord.Interaction, days: int = 30):
        if interaction.channel_id != chat_channel_id:
            await interaction.response.send_message(
                "Use /usage in the chat channel.", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            png_bytes = await asyncio.to_thread(usage_chart.render_usage_chart_png, days)
        except Exception as e:
            logger.error(f"/usage chart render failed: {e}", exc_info=True)
            await interaction.followup.send("Couldn't render the usage chart — check the logs.", ephemeral=True)
            return
        content = None
        limits = token_tracker.get_latest_rate_limits()
        if limits:
            req_remaining = limits.get("anthropic-ratelimit-requests-remaining")
            req_limit = limits.get("anthropic-ratelimit-requests-limit")
            tok_remaining = limits.get("anthropic-ratelimit-tokens-remaining")
            tok_limit = limits.get("anthropic-ratelimit-tokens-limit")
            parts = []
            if req_remaining and req_limit:
                parts.append(f"**{req_remaining}**/{req_limit} requests left this window")
            if tok_remaining and tok_limit:
                parts.append(f"**{tok_remaining}**/{tok_limit} tokens left this window")
            if parts:
                content = "Anthropic-reported: " + " · ".join(parts)
        await interaction.followup.send(
            content=content, file=discord.File(io.BytesIO(png_bytes), filename="usage.png"), ephemeral=True
        )

    async def _post_to(channel_id: int, text: str, fallback_channel_id: int = None):
        """Send `text` to `channel_id` if set, else to `fallback_channel_id` (typically
        the chat channel) if that's set — used so an unconfigured output channel just
        means "goes where it always went" instead of silently vanishing."""
        target_id = channel_id or fallback_channel_id
        if not target_id:
            return
        try:
            channel = await client.fetch_channel(target_id)
        except (discord.NotFound, discord.Forbidden) as e:
            logger.warning(f"Cannot access Discord channel {target_id}: {e}")
            return
        for chunk in _chunk_message(text):
            await channel.send(chunk)

    async def post_to_health(text: str):
        """Exposed for callers outside this module (health_check.py, via
        set_post_fn -- both the scheduled Sunday run and an on-demand "run
        health check" go through this same function) that want to post the
        report without importing Discord internals. No-ops if the client
        isn't connected yet — the health-check loop and Discord's own
        reconnect are scheduled independently, with no ordering guarantee
        (a 4am fire right after a restart could beat Discord).

        One pinned message, edited in place on every run, same pattern as
        refresh_dashboard() -- an embed (not plain text) both for the
        larger size budget (a health report can run longer than a plain
        message's ~2000-char limit) and because the report itself now
        writes **bold** markdown for scannability (see
        weekly-health-check.md), which an embed description renders."""
        if not client.is_ready():
            logger.warning("post_to_health: Discord client not ready, skipping")
            return
        target_channel_id = health_channel_id or chat_channel_id
        if not target_channel_id:
            return
        try:
            channel = await client.fetch_channel(target_channel_id)
        except (discord.NotFound, discord.Forbidden) as e:
            logger.warning(f"Cannot access Discord health channel {target_channel_id}: {e}")
            return

        # report is always "# <title line>\n\n<body>" -- see
        # health_check.run_weekly_health_check(). Title becomes the embed
        # title; body (already <200 words by the instructions file) fits
        # comfortably under an embed description's 4096-char limit.
        title, _, body = text.partition("\n\n")
        embed = discord.Embed(
            title=title.lstrip("#").strip() or "Weekly Health Check",
            description=body.strip(),
            color=discord.Color.green(),
        )
        embed.set_footer(text=HEALTH_MARKER)

        message = None
        if state["health_message_id"]:
            try:
                message = await channel.fetch_message(state["health_message_id"])
            except discord.NotFound:
                message = None

        if message is None:
            # Bot restarted — look for a health message pinned by a previous run
            async for pin in channel.pins(limit=50):
                if pin.author.id == client.user.id and pin.embeds and pin.embeds[0].footer.text and \
                        pin.embeds[0].footer.text.endswith(HEALTH_MARKER):
                    message = pin
                    break

        if message is not None:
            state["health_message_id"] = message.id
            try:
                await message.edit(content=None, embed=embed)
                return
            except discord.NotFound:
                state["health_message_id"] = None

        new_message = await channel.send(embed=embed)
        try:
            await new_message.pin()
        except discord.Forbidden:
            logger.warning("Missing permission to pin the health message — sent unpinned")
        state["health_message_id"] = new_message.id

    client.post_to_health = post_to_health

    async def refresh_usage_dashboard():
        """The Claude usage chart, posted into its own channel if configured
        (falls back to #health, then chat), in the same embed style (title +
        bold-figures description, see post_to_health above), with the
        chart composited in via `set_image`. Posts a new message every time
        rather than editing/replacing a pinned one — with its own dedicated
        channel, the message history itself is the log of past usage snapshots.
        Called on a 6-hour loop (see usage_refresh_loop below)."""
        target_channel_id = usage_channel_id or health_channel_id or chat_channel_id
        if not target_channel_id:
            return
        try:
            channel = await client.fetch_channel(target_channel_id)
        except (discord.NotFound, discord.Forbidden) as e:
            logger.warning(f"Cannot access Discord health channel {target_channel_id}: {e}")
            return

        try:
            png_bytes = await asyncio.to_thread(usage_chart.render_usage_chart_png, 30)
        except Exception as e:
            logger.error(f"usage dashboard: chart render failed: {e}", exc_info=True)
            return

        settings = get_settings()
        today_cost = token_tracker.get_today_usage()["cost"]
        month_cost = token_tracker.get_month_cost()
        description = f"**${today_cost:.2f}** today · **${month_cost:.2f}** this month"
        caps = []
        if settings.daily_spend_cap:
            caps.append(f"**${settings.daily_spend_cap:.2f}**/day")
        if settings.monthly_spend_cap:
            caps.append(f"**${settings.monthly_spend_cap:.2f}**/month")
        if caps:
            description += f" (cap {', '.join(caps)})"

        embed = discord.Embed(
            title="Claude API usage — last 30 days",
            description=description,
            color=discord.Color.blue(),
        )
        embed.set_image(url="attachment://usage.png")

        await channel.send(embed=embed, file=discord.File(io.BytesIO(png_bytes), filename="usage.png"))

    async def check_usage_alerts():
        """Pings the usage channel (falls back to #health, then chat) once
        per day when spend crosses 70% of the self-imposed daily/monthly
        cap, or a key is expiring within a week — same expiry check the
        weekly health report already does, surfaced immediately here
        instead of waiting for Sunday. Tracked by date, not a one-shot
        flag, so a genuinely new day's crossing still alerts even though
        yesterday's already did."""
        target_channel_id = usage_channel_id or health_channel_id or chat_channel_id
        if not target_channel_id:
            return
        today = datetime.now().date().isoformat()
        if state["usage_alert_date"] == today:
            return

        settings = get_settings()
        today_cost = token_tracker.get_today_usage()["cost"]
        month_cost = token_tracker.get_month_cost()
        alerts = []
        if settings.daily_spend_cap and today_cost >= settings.daily_spend_cap * USAGE_ALERT_THRESHOLD:
            alerts.append(
                f"Daily spend at **${today_cost:.2f}** — {USAGE_ALERT_THRESHOLD:.0%}+ of your "
                f"${settings.daily_spend_cap:.2f}/day cap."
            )
        if settings.monthly_spend_cap and month_cost >= settings.monthly_spend_cap * USAGE_ALERT_THRESHOLD:
            alerts.append(
                f"Monthly spend at **${month_cost:.2f}** — {USAGE_ALERT_THRESHOLD:.0%}+ of your "
                f"${settings.monthly_spend_cap:.2f}/month cap."
            )
        for label, raw in expiring_within(7):
            alerts.append(f"**{label}** expires soon: {raw}")

        # Google's Testing-mode refresh tokens expire after 7 days (see
        # google-integration.md) -- without this check that death is silent:
        # get_credentials() just starts returning None and Calendar/Gmail
        # quietly say "not connected" everywhere, with nothing pointing back
        # at "go reconnect on /console". is_connected() actually attempts a
        # refresh, so this doubles as the periodic liveness check
        # is_client_configured()-only startup_summary() can't provide.
        if google_auth.is_client_configured() and not google_auth.is_connected():
            alerts.append(
                "**Google account** is disconnected (Calendar/Gmail) — "
                "visit /console and click \"Connect Google Account\" to reconnect."
            )

        if not alerts:
            return

        state["usage_alert_date"] = today
        await _post_to(target_channel_id, "**Usage alert**\n" + "\n".join(f"- {a}" for a in alerts))

    async def post_to_warnings(text: str):
        """Exposed for callers outside this module (currently pi_companion.py's
        crash-report endpoint, for the Sunny Companion hardware device) that
        want to post to the same #warnings channel this module already uses
        for its own crash notice, without importing Discord internals. Same
        not-ready no-op as post_to_health above, same reason."""
        if not client.is_ready():
            logger.warning("post_to_warnings: Discord client not ready, skipping")
            return
        await _post_to(warnings_channel_id, text, fallback_channel_id=chat_channel_id)

    client.post_to_warnings = post_to_warnings

    async def refresh_dashboard(_change_message: str = None):
        """Post or edit the pinned dashboard message in the dashboard channel
        (read-only — nothing is ever read back from here)."""
        try:
            channel = await client.fetch_channel(dashboard_channel_id)
        except (discord.NotFound, discord.Forbidden) as e:
            logger.warning(f"Cannot access Discord dashboard channel {dashboard_channel_id}: {e}")
            return

        projects_dir = get_settings().project_root / "sunny-vault" / "data" / "projects"
        project_names = sorted(p.name for p in projects_dir.iterdir() if p.is_dir()) if projects_dir.exists() else []
        embed = build_dashboard_embed(tasks_engine.get_dashboard_data(), project_names)

        message = None
        if state["dashboard_message_id"]:
            try:
                message = await channel.fetch_message(state["dashboard_message_id"])
            except discord.NotFound:
                message = None

        if message is None:
            # Bot restarted — look for a dashboard message pinned by a previous run
            async for pin in channel.pins(limit=50):
                if pin.author.id == client.user.id and pin.embeds and pin.embeds[0].footer.text and \
                        pin.embeds[0].footer.text.endswith(DASHBOARD_MARKER):
                    message = pin
                    break

        if message is not None:
            state["dashboard_message_id"] = message.id
            try:
                await message.edit(content=None, embed=embed)
                return
            except discord.NotFound:
                state["dashboard_message_id"] = None

        # Nothing to edit — post a fresh one and pin it
        new_message = await channel.send(embed=embed)
        try:
            await new_message.pin()
        except discord.Forbidden:
            logger.warning("Missing permission to pin the dashboard message — sent unpinned")
        state["dashboard_message_id"] = new_message.id

    async def on_task_change(change_message: str = None):
        """Runs on every successful add/update/delete, from any interface (web
        console, terminal chat, or this bot) — wiring it here covers all of
        them, not just Discord-originated changes."""
        await refresh_dashboard()
        if change_message and task_updates_channel_id:
            await _post_to(task_updates_channel_id, change_message)

    tasks_engine.on_change = on_task_change

    @tasks.loop(minutes=5)
    async def refresh_loop():
        if not service_registry.is_enabled("dashboard_refresh"):
            return
        await refresh_dashboard()

    @tasks.loop(hours=6)
    async def usage_refresh_loop():
        if not service_registry.is_enabled("usage_refresh"):
            return
        await refresh_usage_dashboard()
        await check_usage_alerts()

    @tasks.loop(seconds=VOICE_PRESENCE_INTERVAL_SECONDS)
    async def voice_presence_loop():
        """Reconciles actual voice-connection state against the desired
        state (the "voice_join" service enabled + a channel configured)
        every tick — connects on the first tick after startup, reconnects
        automatically after a drop or a worker crash, disconnects within
        one tick of /service voice_join disable. Replaces the old per-use
        /join/leave commands entirely; there's no manual trigger anymore,
        "Hey Sunny" still gates each individual request once connected."""
        should_be_connected = service_registry.is_enabled("voice_join") and voice_channel_id != 0

        if should_be_connected and not voice_session.is_active():
            channel = client.get_channel(voice_channel_id)
            if channel is None:
                logger.warning(f"voice_presence_loop: configured voice channel {voice_channel_id} not found")
                return
            await voice_session.start(
                channel, tasks_engine, briefing_engine, list_engine, scheduled_engine, project_engine,
                spotify_engine, calendar_engine, notify_fn=_notify_voice_crash,
            )
        elif not should_be_connected and voice_session.is_active():
            await voice_session.stop()

    @tasks.loop(seconds=SCHEDULED_CHECK_INTERVAL_SECONDS)
    async def scheduled_check_loop():
        """Post a ping for any due alarm/reminder — the only real 'sounding'
        mechanism until there's a clock/speaker device. Also looks ahead
        for the next upcoming ALARM (not reminder) and, once it's within
        MORNING_PREP_LOOKAHEAD_SECONDS out, kicks off a background
        briefing_engine.prewarm_morning_briefing() -- so email is pulled
        fresh right before wake-up (see briefing.py's docstring on why)
        without making the alarm ping itself wait on live weather/
        calendar/email calls. state["morning_prep_alarm_id"] tracks which
        alarm occurrence was already prepped, so this only fires once per
        alarm even though the loop itself runs every 30s."""
        now = datetime.now()

        if service_registry.is_enabled("morning_prep") and not service_registry.is_vacation_mode():
            upcoming_alarms = scheduled_engine.db.get_active_items(kind="alarm")
            if upcoming_alarms:
                next_alarm = upcoming_alarms[0]  # get_active_items orders by trigger_at ASC
                seconds_out = (datetime.fromisoformat(next_alarm["trigger_at"]) - now).total_seconds()
                if 0 <= seconds_out <= MORNING_PREP_LOOKAHEAD_SECONDS and state["morning_prep_alarm_id"] != next_alarm["id"]:
                    state["morning_prep_alarm_id"] = next_alarm["id"]
                    asyncio.create_task(briefing_engine.prewarm_morning_briefing())

        if not service_registry.is_enabled("scheduled_check"):
            return

        due = scheduled_engine.db.get_due_items(now)
        if not due:
            return

        try:
            channel = await client.fetch_channel(chat_channel_id)
        except (discord.NotFound, discord.Forbidden) as e:
            logger.warning(f"Cannot access Discord chat channel {chat_channel_id}: {e}")
            return

        for item in due:
            noun = "Alarm" if item["kind"] == "alarm" else "Reminder"
            try:
                await channel.send(f'{noun}: {item["label"]}')
            except discord.Forbidden:
                logger.warning("Missing permission to send scheduled-item ping")

            if item["recurrence"]:
                trigger_at = datetime.fromisoformat(item["trigger_at"])
                scheduled_engine.db.reschedule(item["id"], next_occurrence(trigger_at, item["recurrence"]))
            else:
                scheduled_engine.db.deactivate(item["id"])

    @tasks.loop(seconds=CLASS_REMINDERS_CHECK_INTERVAL_SECONDS)
    async def class_reminders_loop():
        """Pings #reminders (or chat, if unconfigured) 2 days before and
        the day of every tracked class due date/exam -- see
        class_deadlines.check_and_notify() for the actual gating logic
        that keeps this from double-posting."""
        if not service_registry.is_enabled("class_reminders"):
            return

        async def post(text: str):
            await _post_to(reminders_channel_id, text, fallback_channel_id=chat_channel_id)

        await class_deadlines.check_and_notify(post)

    @client.event
    async def on_ready():
        logger.info(
            f"Discord bot connected as {client.user} "
            f"(chat channel: {chat_channel_id}, dashboard: {dashboard_channel_id})"
        )
        if not refresh_loop.is_running() and service_registry.is_autostart("dashboard_refresh"):
            refresh_loop.start() # runs immediately, then every 5 minutes
        # scheduled_check_loop also drives morning-prep lookahead, not just
        # alarms/reminders -- always start it and let the per-tick is_enabled
        # checks above decide what actually happens, since gating the whole
        # loop on either service's autostart flag alone would silently kill
        # the other one too.
        if not scheduled_check_loop.is_running():
            scheduled_check_loop.start() # runs immediately, then every 30s
        if not usage_refresh_loop.is_running() and service_registry.is_autostart("usage_refresh"):
            usage_refresh_loop.start() # runs immediately, then every 6 hours
        # Gated on voice_channel_id (a hard prerequisite -- nothing to
        # connect to without it), not is_autostart("voice_join"): the
        # per-tick is_enabled() check inside the loop is what /service
        # voice_join enable|disable actually controls, same reasoning as
        # scheduled_check_loop above.
        if not voice_presence_loop.is_running() and voice_channel_id:
            voice_presence_loop.start() # runs immediately, then every 30s
        if not class_reminders_loop.is_running() and service_registry.is_autostart("class_reminders"):
            class_reminders_loop.start() # runs immediately, then every few hours

        # Guild-scoped sync (instant) rather than global (~1hr to propagate) —
        # this bot is single-server by design already (see discord-bot.md).
        # copy_global_to() is required first: commands defined with
        # @tree.command() (no guild=) are global commands, and tree.sync(
        # guild=...) alone only uploads that guild's OWN command list, which
        # starts empty — it does not implicitly copy global commands in.
        # Guarded so a reconnect doesn't re-sync every time.
        if not state["commands_synced"] and client.guilds:
            state["commands_synced"] = True
            guild = client.guilds[0]
            try:
                tree.copy_global_to(guild=guild)
                synced = await tree.sync(guild=guild)
                logger.info(f"Synced {len(synced)} slash command(s) to guild {guild.id}")
            except discord.HTTPException as e:
                logger.error(f"Slash command sync failed: {e}", exc_info=True)

        # Post what's still missing an API key once per run, so it's visible —
        # in #warnings if configured, else the chat channel like before that
        # existed. Skipped entirely if everything's configured (no noise).
        if not state["posted_key_status"]:
            state["posted_key_status"] = True
            missing = missing_api_keys()
            if missing:
                await _post_to(warnings_channel_id, startup_summary(), fallback_channel_id=chat_channel_id)

        # A crash (native abort, segfault, OOM-kill) leaves no trace in
        # sunny.log or anywhere else the app already looks — see
        # crash_check.py for why. Surfacing it here means an actual crash
        # is visible in Discord on the very next startup, not only by
        # someone reading journalctl by hand.
        if not state["posted_crash_notice"]:
            state["posted_crash_notice"] = True
            crash_signature = check_previous_crash()
            if crash_signature:
                await _post_to(
                    warnings_channel_id,
                    f"I crashed and restarted. Last run ended with: `{crash_signature}`",
                    fallback_channel_id=chat_channel_id,
                )

    async def _post_storm_update(text: str) -> None:
        await _post_to(chat_channel_id, text)

    @client.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != chat_channel_id:
            return

        lowered = message.content.strip().lower()

        # Storm mode: checked before the shared assistant router and before
        # server-admin commands, same reasoning as both -- it's a Discord-
        # only, proactive-posting feature (see storm_mode.py's own module
        # docstring for why handle_message() can't express it), not a
        # request/response answer.
        if state["storm_wizard"] is not None:
            step = state["storm_wizard"]["step"]
            if lowered in _WIZARD_CANCEL_WORDS:
                state["storm_wizard"] = None
                await message.channel.send("No worries — cancelled.")
                return
            if step == "interval":
                minutes = storm_mode.parse_minutes(message.content)
                if minutes is None:
                    await message.channel.send(
                        'Didn\'t catch an interval — try something like "10 minutes" or "1 hour".'
                    )
                    return
                state["storm_wizard"] = {"step": "duration", "interval": minutes}
                await message.channel.send("How long should storm mode run before it turns off automatically?")
                return
            # step == "duration" -- the wizard's last step
            duration = storm_mode.parse_minutes(message.content)
            if duration is None:
                await message.channel.send(
                    'Didn\'t catch a duration — try something like "2 hours" or "90 minutes".'
                )
                return
            interval = state["storm_wizard"]["interval"]
            state["storm_wizard"] = None
            await storm_mode.start(interval, duration, _post_storm_update)
            await message.channel.send(f"Storm mode on — updates every {interval} min for {duration} min.")
            return

        if lowered in _STORM_MODE_STATUS_TRIGGERS:
            await message.channel.send(storm_mode.status() or "Storm mode isn't running.")
            return

        if lowered in _STORM_MODE_STOP_TRIGGERS:
            stopped = await storm_mode.stop(_post_storm_update)
            if not stopped:
                await message.channel.send("Storm mode isn't running.")
            return

        if lowered in _STORM_MODE_TRIGGERS:
            state["storm_wizard"] = {"step": "interval"}
            await message.channel.send('How often should I update you? (e.g. "10 minutes")')
            return

        # Checked before the shared assistant router, same reason lists/alarms
        # are checked before tasks there: a generic "delete <title>" pattern
        # would otherwise swallow "delete channel #general" as a task-delete
        # attempt. Guild-scoped, so this only ever matches here, never on the
        # console or terminal chat.
        admin_command = ServerAdminParser.parse(message.content)
        if admin_command is not None:
            action, data = admin_command
            response = await _execute_server_admin(action, data, message.guild, chat_channel_id)
            for chunk in _chunk_message(response):
                await message.channel.send(chunk)
            return

        effective_text, pdf_error = await _resolve_message_text(message)
        if pdf_error is not None:
            await message.channel.send(pdf_error)
            return

        session_id = f"discord:{message.channel.id}:{message.author.id}"
        response = await handle_message(
            effective_text, tasks_engine, briefing_engine, list_engine, scheduled_engine,
            project_engine, spotify_engine, calendar_engine, session_id=session_id
        )
        # Dashboard refresh (if this was a mutating command) happens automatically
        # via tasks_engine.on_change — no need to check/trigger it here too.

        if is_briefing_trigger(message.content):
            embed = build_briefing_embed(response)
            await message.channel.send(embed=embed)
            if briefings_channel_id:
                try:
                    briefings_channel = await client.fetch_channel(briefings_channel_id)
                    await briefings_channel.send(embed=embed)
                except (discord.NotFound, discord.Forbidden) as e:
                    logger.warning(f"Cannot access Discord briefings channel {briefings_channel_id}: {e}")
        else:
            for chunk in _chunk_message(response):
                await message.channel.send(chunk)

    return client
