"""Live Google Calendar reads — today's events off the primary calendar.

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


def get_events(day_offset: int = 0) -> Optional[List[Dict]]:
    """Events for today (day_offset=0) or another day, or None if unavailable.

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
        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
    except HttpError as e:
        logger.error(f"Google Calendar API error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error calling Google Calendar: {e}", exc_info=True)
        return None

    return [_format_event(e) for e in result.get("items", [])]
