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
        return None
    except Exception as e:
        logger.error(f"Unexpected error calling Gmail: {e}", exc_info=True)
        return None

    return {
        "unread_count": unread_count,
        "urgent_count": urgent_count,
        "top_subjects": top_subjects,
    }
