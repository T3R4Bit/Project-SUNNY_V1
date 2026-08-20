"""Live Google Calendar reads — today's events across every calendar the
account has, not just the primary one.

Read-only (calendar.readonly scope, see google_auth.SCOPES). Every call is
wrapped so a Google-side failure (expired grant, network error, API outage)
degrades to "no data" rather than crashing the briefing — see the "fail
quietly" principle in sunny-vault/docs/architecture/briefing-engine.md.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from sunny_code.components import google_auth

logger = logging.getLogger(__name__)


def _service():
    creds = google_auth.get_credentials()
    if creds is None:
        return None
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _format_event(event: dict) -> Dict:
    start = event.get("start", {})
    raw = start.get("dateTime", start.get("date"))
    time_str = "All day"
    if start.get("dateTime"):
        try:
            time_str = datetime.fromisoformat(raw).strftime("%-I:%M%p").lower()
        except ValueError:
            time_str = raw
    return {
        "time": time_str,
        "title": event.get("summary", "(no title)"),
        "location": event.get("location", ""),
        "duration": "",
    }


def _event_sort_key(event: dict):
    """All-day events first, then timed events in actual chronological order —
    sorting on the formatted display string instead (e.g. "9:40am" vs
    "10:00am") would sort lexicographically and put 10am before 9am."""
    start = event.get("start", {})
    if start.get("dateTime"):
        return (1, datetime.fromisoformat(start["dateTime"]))
    return (0, datetime.fromisoformat(start.get("date", "9999-12-31")))


def _list_calendar_ids(service) -> List[str]:
    result = service.calendarList().list().execute()
    return [c["id"] for c in result.get("items", [])]


def get_events(day_offset: int = 0) -> Optional[List[Dict]]:
    """Events for today (day_offset=0) or another day, across every calendar
    the account has — not just "primary". A personal Google account commonly
    has several (family, shared, subject-specific) with real events on them;
    querying only "primary" silently misses whatever's not on it. Returns
    None if unavailable.

    None means "couldn't reach Calendar" (not connected, or a live error) —
    callers should treat that the same as the "not connected" case, never crash.
    """
    service = _service()
    if service is None:
        return None

    # datetime.now() is naive local time; .astimezone() attaches the system's
    # actual local UTC offset. Building the day boundary from that and calling
    # .isoformat() (no "Z" appended) produces a correct offset-aware
    # timestamp — appending a literal "Z" here would mislabel local midnight
    # as UTC midnight, a real bug: on this server (EDT, UTC-4) that silently
    # shifted the query window by 4 hours, so events near the start/end of
    # the day could fall outside it and never show up.
    now_local = datetime.now().astimezone()
    day = (now_local + timedelta(days=day_offset)).date()
    tz = now_local.tzinfo
    time_min = datetime.combine(day, datetime.min.time(), tzinfo=tz).isoformat()
    time_max = datetime.combine(day, datetime.max.time(), tzinfo=tz).isoformat()

    try:
        calendar_ids = _list_calendar_ids(service)
    except HttpError as e:
        logger.error(f"Google Calendar API error listing calendars: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error listing calendars: {e}", exc_info=True)
        return None

    raw_events = []
    for calendar_id in calendar_ids:
        try:
            result = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
        except HttpError as e:
            # One calendar erroring (e.g. a permission quirk on a shared one)
            # shouldn't blank out events from every other calendar.
            logger.warning(f"Google Calendar API error on {calendar_id}: {e}")
            continue
        raw_events.extend(result.get("items", []))

    raw_events.sort(key=_event_sort_key)
    return [_format_event(e) for e in raw_events]
