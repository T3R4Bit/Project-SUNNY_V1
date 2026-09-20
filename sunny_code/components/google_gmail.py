"""Live Gmail reads — unread/urgent counts and subject lines.

Read-only (gmail.readonly scope, see google_auth.SCOPES) — this only ever
reads headers, never bodies, and never sends. "Urgent" is Gmail's own
`is:important` classification, not LLM-judged (matches the briefing engine's
"LLM only if interpretation is needed" principle — this doesn't need it).
Same fail-quietly contract as google_calendar: any error returns None.
"""

import logging
from typing import Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from sunny_code.components import google_auth

logger = logging.getLogger(__name__)

_TOP_SUBJECTS_LIMIT = 5

# Why the last Gmail call failed, for the dashboard to show. get_summary()
# and get_flagged() both return None on failure by contract, which tells a
# caller that something went wrong but not what -- and the difference
# between "not signed in", "token expired" and "the Gmail API isn't
# enabled in the Google Cloud project" is the difference between three
# completely different fixes. Confirmed necessary 2026-09-20: the real
# cause was a 403 accessNotConfigured (Gmail API never enabled on the
# project), while the dashboard was guessing at an expired token.
last_error_reason: Optional[str] = None


def _record_error(exc) -> None:
    """Store a short, human-actionable reason from a Gmail HttpError."""
    global last_error_reason
    text = str(exc)
    if "accessNotConfigured" in text or "has not been used in project" in text:
        last_error_reason = (
            "The Gmail API isn't enabled for this Google Cloud project. "
            "Enable it in the Cloud Console (APIs & Services -> Library -> "
            "Gmail API), wait a minute, then retry. Calendar works because "
            "its API is enabled separately."
        )
    elif "invalid_grant" in text or "Token has been expired" in text:
        last_error_reason = "The Google token expired or was revoked — reconnect at /auth/google/login."
    elif "insufficientPermissions" in text or "ACCESS_TOKEN_SCOPE_INSUFFICIENT" in text:
        last_error_reason = (
            "The stored Google token predates the gmail.readonly scope — "
            "reconnect at /auth/google/login to re-consent."
        )
    elif "403" in text:
        last_error_reason = f"Gmail refused the request (403). {text[:160]}"
    else:
        last_error_reason = f"{type(exc).__name__}: {text[:160]}"


def _service():
    creds = google_auth.get_credentials()
    if creds is None:
        return None
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _count(service, query: str) -> int:
    result = service.users().messages().list(userId="me", q=query, maxResults=1).execute()
    return result.get("resultSizeEstimate", 0)


def _header(headers: List[Dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def get_summary() -> Optional[Dict]:
    """Unread/urgent counts + a few subject lines, or None if Gmail is unavailable."""
    service = _service()
    if service is None:
        return None

    try:
        unread_count = _count(service, "is:unread")
        urgent_count = _count(service, "is:unread is:important")

        top_subjects = []
        if unread_count:
            recent = (
                service.users()
                .messages()
                .list(userId="me", q="is:unread", maxResults=_TOP_SUBJECTS_LIMIT)
                .execute()
                .get("messages", [])
            )
            for msg in recent:
                detail = (
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=msg["id"],
                        format="metadata",
                        metadataHeaders=["From", "Subject"],
                    )
                    .execute()
                )
                headers = detail.get("payload", {}).get("headers", [])
                top_subjects.append(
                    {"from": _header(headers, "From"), "subject": _header(headers, "Subject")}
                )
    except HttpError as e:
        logger.error(f"Gmail API error: {e}", exc_info=True)
        _record_error(e)
        return None
    except Exception as e:
        logger.error(f"Unexpected error calling Gmail: {e}", exc_info=True)
        return None

    return {
        "unread_count": unread_count,
        "urgent_count": urgent_count,
        "top_subjects": top_subjects,
    }


def get_flagged(limit: int = 5) -> Optional[List[Dict]]:
    """Structured flagged-mail list for external dashboards (e.g. keaton.dev):
    important unread first (flag URGENT), topped up with other unread (flag
    LATER) up to `limit`. None if Gmail is unavailable — same fail-quietly
    contract as get_summary()."""
    service = _service()
    if service is None:
        return None

    def _fetch(query: str, need: int, seen: set) -> List[Dict]:
        if need <= 0:
            return []
        msgs = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=need + len(seen))
            .execute()
            .get("messages", [])
        )
        out = []
        for msg in msgs:
            if msg["id"] in seen or len(out) >= need:
                continue
            detail = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject"],
                )
                .execute()
            )
            headers = detail.get("payload", {}).get("headers", [])
            seen.add(msg["id"])
            out.append(
                {"subject": _header(headers, "Subject") or "(no subject)", "from": _header(headers, "From")}
            )
        return out

    try:
        seen: set = set()
        urgent = _fetch("is:unread is:important", limit, seen)
        for m in urgent:
            m["flag"] = "URGENT"
        later = _fetch("is:unread", limit - len(urgent), seen)
        for m in later:
            m["flag"] = "LATER"
    except HttpError as e:
        logger.error(f"Gmail API error in get_flagged: {e}", exc_info=True)
        _record_error(e)
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_flagged: {e}", exc_info=True)
        return None

    return urgent + later
