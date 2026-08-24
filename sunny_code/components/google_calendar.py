"""Live Google Calendar reads and writes — reads span every calendar the
account has, not just the primary one; writes (create_event/delete_event)
go through calendar_engine.py's natural-language layer, called directly
here only for the actual API calls.

Full `calendar` scope, not just calendar.readonly (see google_auth.SCOPES —
widened specifically so create_event/delete_event below can work). Every
call is wrapped so a Google-side failure (expired grant, network error, API
outage) degrades to "no data"/False rather than crashing the caller — see
the "fail quietly" principle in sunny-vault/docs/architecture/briefing-engine.md.
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
    # datetime.now() is naive local time; .astimezone() attaches the system's
    # actual local UTC offset. Building the day boundary from that produces a
    # correct offset-aware timestamp — appending a literal "Z" here would
    # mislabel local midnight as UTC midnight, a real bug: on this server
    # (EDT, UTC-4) that silently shifted the query window by 4 hours, so
    # events near the start/end of the day could fall outside it and never
    # show up.
    now_local = datetime.now().astimezone()
    day = (now_local + timedelta(days=day_offset)).date()
    tz = now_local.tzinfo
    time_min = datetime.combine(day, datetime.min.time(), tzinfo=tz)
    time_max = datetime.combine(day, datetime.max.time(), tzinfo=tz)

    raw_events = get_events_range(time_min, time_max)
    if raw_events is None:
        return None

    raw_events.sort(key=_event_sort_key)
    return [_format_event(e) for e in raw_events]


def get_events_range(time_min: datetime, time_max: datetime) -> Optional[List[Dict]]:
    """Raw (unformatted) events across every calendar the account has,
    between time_min and time_max — both must be timezone-aware. Shared
    plumbing between get_events() (today's schedule, then display-formatted
    via _format_event()) and anything that needs a wider window, e.g.
    detecting recurring events (a semester's worth of class meetings) across
    months rather than one day. Returns raw Google event dicts (summary,
    start, end, recurringEventId, etc.), not get_events()'s formatted ones —
    callers that want that formatting should call _format_event() themselves.
    None means "couldn't reach Calendar," same fail-quiet contract as
    get_events()."""
    service = _service()
    if service is None:
        return None

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
                    timeMin=time_min.isoformat(),
                    timeMax=time_max.isoformat(),
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

    return raw_events


def create_event(title: str, start: datetime, duration_minutes: int = 60, calendar_id: str = "primary") -> Optional[dict]:
    """Creates a new event on `calendar_id` (default: the account's primary
    calendar — a reasonable default for a general "add X to my calendar",
    unlike get_events() above, which reads every calendar since a personal
    account commonly has several with real events on them). `start` is a
    naive local datetime (e.g. from time_parse.parse_time_expression) —
    .astimezone() attaches the system's real local UTC offset, same trick
    get_events() uses for its own day-boundary query. Returns the created
    event dict, or None if unavailable/failed — same fail-quiet contract as
    get_events()."""
    service = _service()
    if service is None:
        return None

    start_local = start.astimezone()
    end_local = (start + timedelta(minutes=duration_minutes)).astimezone()
    body = {
        "summary": title,
        "start": {"dateTime": start_local.isoformat()},
        "end": {"dateTime": end_local.isoformat()},
    }
    try:
        return service.events().insert(calendarId=calendar_id, body=body).execute()
    except HttpError as e:
        logger.error(f"Google Calendar API error creating event: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error creating event: {e}", exc_info=True)
        return None


def find_event_by_title(title: str, days_ahead: int = 14) -> Optional[Dict]:
    """Searches every calendar the account has, from right now through
    `days_ahead` days out, for a case-insensitive substring match on the
    event title — soonest match wins when more than one matches. Returns
    {"calendar_id", "event_id", "title"} for delete_event() below, or None
    if nothing matched (or Calendar's unreachable). Google's own `q=` search
    parameter also matches description/location, so results still get a
    stricter client-side title check rather than trusting `q=` alone."""
    service = _service()
    if service is None:
        return None

    now_local = datetime.now().astimezone()
    time_min = now_local.isoformat()
    time_max = (now_local + timedelta(days=days_ahead)).isoformat()

    try:
        calendar_ids = _list_calendar_ids(service)
    except HttpError as e:
        logger.error(f"Google Calendar API error listing calendars: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error listing calendars: {e}", exc_info=True)
        return None

    needle = title.strip().lower()
    candidates = []
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
                    q=title,
                )
                .execute()
            )
        except HttpError as e:
            logger.warning(f"Google Calendar API error searching {calendar_id}: {e}")
            continue
        for event in result.get("items", []):
            if needle in event.get("summary", "").lower():
                candidates.append((calendar_id, event))

    if not candidates:
        return None

    calendar_id, event = min(candidates, key=lambda pair: _event_sort_key(pair[1]))
    return {
        "calendar_id": calendar_id,
        "event_id": event["id"],
        "title": event.get("summary", "(no title)"),
    }


def delete_event(calendar_id: str, event_id: str) -> bool:
    """Deletes one event by id (from find_event_by_title() above). Returns
    False on any failure, same fail-quiet contract as everything else here —
    never raises to the caller."""
    service = _service()
    if service is None:
        return False
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return True
    except HttpError as e:
        logger.error(f"Google Calendar API error deleting event: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error deleting event: {e}", exc_info=True)
        return False
