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

Three real slash commands — /speak (Piper TTS, one-shot text-to-audio
attachment), /join and /leave (live voice-channel conversation via
stt.py/voice_session.py — see sunny-vault/docs/architecture/voice-join.md).
Everything else here is plain-text via handle_message(). Registered via a
discord.app_commands.CommandTree bound directly to this bare discord.Client
(no commands.Bot needed), synced to this bot's one guild in on_ready.

Setup steps: see sunny-vault/docs/architecture/discord-bot.md
"""

import asyncio
import io
import logging
from datetime import datetime
from typing import Literal

import discord
from discord.ext import tasks

from sunny_code.components import category_store, token_tracker, tts, usage_chart, voice_session
from sunny_code.components.assistant import handle_message, is_briefing_trigger
from sunny_code.components.briefing import BriefingEngine
from sunny_code.components.crash_check import check_previous_crash
from sunny_code.components.key_status import expiring_within, missing_api_keys, startup_summary
from sunny_code.components.lists_engine import ListEngine
from sunny_code.components.project_engine import ProjectEngine
from sunny_code.components.scheduled_engine import ScheduledEngine
from sunny_code.components.server_admin_parser import ServerAdminParser
from sunny_code.components.spotify_engine import SpotifyEngine
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
USAGE_MARKER = "‌" # zero-width non-joiner (U+200C) -- a third distinct
# invisible marker, same reasoning as HEALTH_MARKER. Lives in the plain
# message content (not a footer) since the usage message's payload is an
# image attachment, which has no embed/footer to hide a marker in.
USAGE_ALERT_THRESHOLD = 0.7 # fraction of daily_spend_cap/monthly_spend_cap
# that triggers a ping -- "70%" per the backlog item this implements
MAX_MESSAGE_LENGTH = 1900 # Discord's real limit is 2000; leave headroom
SCHEDULED_CHECK_INTERVAL_SECONDS = 30
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


def build_dashboard_embed(dashboard_data: dict, project_names: list) -> discord.Embed:
    """Renders TaskEngine.get_dashboard_data() as a Discord embed — one
    field per active category, plus a Projects field listing whatever
    project folders exist on disk (populated by the "new project" flow;
    project_names is a plain directory listing the caller supplies, not
    something this function reads itself, so it's testable without a real
    vault on disk). Tasks don't get a priority bar; the priority number is
    enough. Module-level (not a closure in create_discord_bot()) so this
    can be unit-tested directly with synthetic data."""
    stats = dashboard_data["stats"]

    due_soon = dashboard_data["due_soon"]
    description = f"{len(due_soon)} task{'s' if len(due_soon) != 1 else ''} due this week" if due_soon else None
    embed = discord.Embed(title="Your Tasks", description=description, color=discord.Color.blurple())

    for tag, tag_tasks in dashboard_data["categories"]:
        lines = []
        for task in tag_tasks[:5]:
            due_str = f" (due {task['due_date']})" if task["due_date"] else ""
            lines.append(f"P{task['priority']} — {task['title']}{due_str}")
        if len(tag_tasks) > 5:
            lines.append(f"...and {len(tag_tasks) - 5} more")
        embed.add_field(name=f"{tag} ({len(tag_tasks)})", value="\n".join(lines) or "(none)", inline=False)

    embed.add_field(name="Projects", value="\n".join(project_names) if project_names else "(none yet)", inline=False)

    embed.set_footer(
        text=f"Open: {stats['open']} | In Progress: {stats['in_progress']} | Done: {stats['done']}{DASHBOARD_MARKER}"
    )
    return embed


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
    chat_channel_id: int,
    dashboard_channel_id: int = 0,
    briefings_channel_id: int = 0,
    warnings_channel_id: int = 0,
    task_updates_channel_id: int = 0,
    health_channel_id: int = 0,
    usage_channel_id: int = 0,
) -> discord.Client:
    """Build (but don't start) the Discord client. chat_channel_id is the only
    channel commands are read from. dashboard_channel_id is where the pinned
    task dashboard lives — falls back to chat_channel_id if unset, so leaving
    it unconfigured reproduces the old single-channel behavior exactly. The
    remaining optional *_channel_id args are output-only destinations —
    see sunny-vault/docs/architecture/discord-bot.md."""
    dashboard_channel_id = dashboard_channel_id or chat_channel_id

    intents = discord.Intents.default()
    intents.message_content = True # required to read command text, not just embeds/mentions

    client = discord.Client(intents=intents)
    tree = discord.app_commands.CommandTree(client)
    client.tree = tree # exposed for introspection/testing, and for future slash commands (e.g. /join) to extend
    state = {
        "dashboard_message_id": None,
        "health_message_id": None,
        "usage_message_id": None,
        "usage_alert_date": None,
        "posted_key_status": False,
        "commands_synced": False,
        "posted_crash_notice": False,
    }

    @tree.command(name="speak", description="Speak this text out loud (Piper TTS, posted as an audio attachment)")
    async def speak_command(interaction: discord.Interaction, text: str):
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
        try:
            wav_bytes = await asyncio.to_thread(tts.synthesize_wav_bytes, text)
        except Exception as e:
            logger.error(f"/speak synthesis failed: {e}")
            await interaction.followup.send("Couldn't synthesize that — check the logs.", ephemeral=True)
            return
        await interaction.followup.send(
            file=discord.File(io.BytesIO(wav_bytes), filename="speech.wav"), ephemeral=True
        )

    @tree.command(name="join", description="Join your voice channel for a live conversation (Vosk STT + Piper TTS)")
    async def join_command(interaction: discord.Interaction):
        """Live conversation, not one-shot like /speak — see
        sunny-vault/docs/architecture/voice-join.md. Same channel
        restriction as every other command (the command itself is typed
        in the chat channel; the bot then joins whichever voice channel
        the caller is currently in)."""
        if interaction.channel_id != chat_channel_id:
            await interaction.response.send_message(
                "Use /join in the chat channel.", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True, ephemeral=True)

        async def _notify_voice_crash(text: str):
            # /join's voice pipeline now runs in an isolated worker
            # process specifically so a native crash there can't take
            # the rest of the bot down with it — this is how that still
            # becomes visible in Discord right away, same channel as
            # every other warning. See voice_session.py/voice_worker.py.
            await _post_to(warnings_channel_id, text, fallback_channel_id=chat_channel_id)

        message = await voice_session.start(
            interaction, tasks_engine, briefing_engine, list_engine, scheduled_engine, project_engine,
            spotify_engine, notify_fn=_notify_voice_crash
        )
        await interaction.followup.send(message, ephemeral=True)

    @tree.command(name="leave", description="Leave the voice channel")
    async def leave_command(interaction: discord.Interaction):
        if interaction.channel_id != chat_channel_id:
            await interaction.response.send_message(
                "Use /leave in the chat channel.", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        message = await voice_session.stop()
        await interaction.followup.send(message, ephemeral=True)

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
            logger.error(f"/usage chart render failed: {e}")
            await interaction.followup.send("Couldn't render the usage chart — check the logs.", ephemeral=True)
            return
        await interaction.followup.send(
            file=discord.File(io.BytesIO(png_bytes), filename="usage.png"), ephemeral=True
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
        """One pinned message with the Claude usage chart as an image
        attachment, edited in place on every run — same pattern as
        refresh_dashboard()/post_to_health(), except the payload is an
        image, not text/an embed, so the pin-rediscovery marker lives in
        the message's plain content (an attachment has no footer to hide
        it in). Called on an hourly loop (see usage_refresh_loop below),
        same "runs immediately, then every N" shape as the task dashboard's
        own 5-minute backstop."""
        target_channel_id = usage_channel_id or chat_channel_id
        if not target_channel_id:
            return
        try:
            channel = await client.fetch_channel(target_channel_id)
        except (discord.NotFound, discord.Forbidden) as e:
            logger.warning(f"Cannot access Discord usage channel {target_channel_id}: {e}")
            return

        try:
            png_bytes = await asyncio.to_thread(usage_chart.render_usage_chart_png, 30)
        except Exception as e:
            logger.error(f"usage dashboard: chart render failed: {e}")
            return

        content = f"Claude API usage — last 30 days{USAGE_MARKER}"

        message = None
        if state["usage_message_id"]:
            try:
                message = await channel.fetch_message(state["usage_message_id"])
            except discord.NotFound:
                message = None

        if message is None:
            # Bot restarted — look for a usage message pinned by a previous run
            async for pin in channel.pins(limit=50):
                if pin.author.id == client.user.id and pin.content.endswith(USAGE_MARKER):
                    message = pin
                    break

        if message is not None:
            state["usage_message_id"] = message.id
            try:
                await message.edit(
                    content=content, attachments=[discord.File(io.BytesIO(png_bytes), filename="usage.png")]
                )
                return
            except discord.NotFound:
                state["usage_message_id"] = None

        new_message = await channel.send(content=content, file=discord.File(io.BytesIO(png_bytes), filename="usage.png"))
        try:
            await new_message.pin()
        except discord.Forbidden:
            logger.warning("Missing permission to pin the usage message — sent unpinned")
        state["usage_message_id"] = new_message.id

    async def check_usage_alerts():
        """Pings the usage channel once per day when spend crosses 70% of
        the self-imposed daily/monthly cap, or a key is expiring within a
        week — same expiry check the weekly health report already does,
        surfaced immediately here instead of waiting for Sunday. Tracked
        by date, not a one-shot flag, so a genuinely new day's crossing
        still alerts even though yesterday's already did."""
        target_channel_id = usage_channel_id or chat_channel_id
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

        projects_dir = get_settings().project_root / "sunny-vault" / "projects"
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
        await refresh_dashboard()

    @tasks.loop(hours=1)
    async def usage_refresh_loop():
        await refresh_usage_dashboard()
        await check_usage_alerts()

    @tasks.loop(seconds=SCHEDULED_CHECK_INTERVAL_SECONDS)
    async def scheduled_check_loop():
        """Post a ping for any due alarm/reminder — the only real 'sounding'
        mechanism until there's a clock/speaker device."""
        due = scheduled_engine.db.get_due_items(datetime.now())
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

    @client.event
    async def on_ready():
        logger.info(
            f"Discord bot connected as {client.user} "
            f"(chat channel: {chat_channel_id}, dashboard: {dashboard_channel_id})"
        )
        if not refresh_loop.is_running():
            refresh_loop.start() # runs immediately, then every 5 minutes
        if not scheduled_check_loop.is_running():
            scheduled_check_loop.start() # runs immediately, then every 30s
        if not usage_refresh_loop.is_running():
            usage_refresh_loop.start() # runs immediately, then every hour

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
                logger.error(f"Slash command sync failed: {e}")

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

    @client.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != chat_channel_id:
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

        session_id = f"discord:{message.channel.id}:{message.author.id}"
        response = await handle_message(
            message.content, tasks_engine, briefing_engine, list_engine, scheduled_engine,
            project_engine, spotify_engine, session_id=session_id
        )
        for chunk in _chunk_message(response):
            await message.channel.send(chunk)
        # Dashboard refresh (if this was a mutating command) happens automatically
        # via tasks_engine.on_change — no need to check/trigger it here too.

        if briefings_channel_id and is_briefing_trigger(message.content):
            await _post_to(briefings_channel_id, response)

    return client
