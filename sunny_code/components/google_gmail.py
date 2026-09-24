"""Live Gmail reads — unread/urgent counts and subject lines.

Read-only (gmail.readonly scope, see google_auth.SCOPES) — this only ever
reads headers, never bodies, and never sends. "Urgent" is Gmail's own
`is:important` classification, not LLM-judged (matches the briefing engine's
"LLM only if interpretation is needed" principle — this doesn't need it).
Same fail-quietly contract as google_calendar: any error returns None.
"""

import logging
from typing import Dict, List, Optional, Tuple

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


# Paging cap. Each page is 500 ids, so this is at most 4 extra API calls
# for the unread total, once per brief.
_COUNT_CAP = 2000


def _count(service, query: str, cap: int = _COUNT_CAP) -> Tuple[int, bool]:
    """(count, was_capped) for a query.

    Pages real message ids rather than trusting resultSizeEstimate, which
    is an estimate in name only: measured on this mailbox 2026-09-24 it
    returned 201 for BOTH "is:unread" and the filtered important query,
    while the true counts were 2500 and 83. The brief was rendering that
    as "201 unread (201 marked important)" -- a number that is not just
    wrong but self-evidently wrong, since it claims every unread message
    is important.

    Capped because an inbox can be arbitrarily large and a count is not
    worth unbounded paging. The flag lets the caller render "2000+"
    instead of silently understating it.
    """
    total = 0
    token = None
    while True:
        result = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=500, pageToken=token)
            .execute()
        )
        total += len(result.get("messages", []))
        token = result.get("nextPageToken")
        if not token or total >= cap:
            return (total, bool(token))


def _header(headers: List[Dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


# Gmail's own is:important is generous -- it was flagging Prusa's "15% Off
# Prusament" and Peak Design's "All the power. Way less brick." as URGENT
# alongside a recruiter reply. Two filters cut that, and they cut it in
# different places on purpose:
#
#   1. Category exclusions, IN THE QUERY, so the promotional mail never
#      comes back over the wire and costs no metadata fetch.
#   2. List-Unsubscribe, CLIENT-SIDE, because Gmail search cannot match on
#      an arbitrary header. Bulk senders are required to set it and real
#      person-to-person mail does not, which caught three more (a job-alert
#      newsletter, a recruiting blast, Resume Now) that Gmail had not
#      categorised as promotions.
#
# Measured on the live mailbox 2026-09-24: the top of the list went from
# two marketing blasts to a recruiter, a professor, two advisors and a
# parking decision. One straggler (an AliExpress notice) defeats both,
# since it strips List-Unsubscribe and is not categorised -- caught by
# neither filter and left alone rather than special-cased by sender, which
# would be a blocklist nobody maintains.
IMPORTANT_QUERY = (
    "is:unread is:important "
    "-category:promotions -category:social -category:updates"
)

# Same exclusions without the importance requirement, for topping a list
# up. Without them the top-up was pure marketing, which is how a five-item
# list ends up with one real message in it.
UNREAD_QUERY = "is:unread -category:promotions -category:social -category:updates"

_BULK_HEADERS = ["From", "Subject", "List-Unsubscribe", "Precedence"]


def _is_bulk(headers: List[Dict]) -> bool:
    """Whether a message is bulk mail rather than addressed to a person."""
    if _header(headers, "List-Unsubscribe"):
        return True
    return (_header(headers, "Precedence") or "").lower() in ("bulk", "list", "junk")


def get_summary() -> Optional[Dict]:
    """Unread/urgent counts + a few subject lines, or None if Gmail is unavailable."""
    service = _service()
    if service is None:
        return None

    try:
        # unread_count stays the HONEST total -- "you have 41 unread" is a
        # different fact from "3 of them matter", and collapsing the two
        # would hide the size of the inbox.
        unread_count, unread_capped = _count(service, "is:unread")
        urgent_count, _ = _count(service, IMPORTANT_QUERY)

        top_subjects = []
        if unread_count:
            # Was plain "is:unread" -- completely unfiltered, so the brief
            # listed whatever arrived most recently, marketing included.
            # Over-fetched because bulk mail is dropped below.
            recent = (
                service.users()
                .messages()
                .list(userId="me", q=IMPORTANT_QUERY, maxResults=_TOP_SUBJECTS_LIMIT * 3)
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
                        metadataHeaders=_BULK_HEADERS,
                    )
                    .execute()
                )
                headers = detail.get("payload", {}).get("headers", [])
                if _is_bulk(headers):
                    continue
                top_subjects.append(
                    {"from": _header(headers, "From"), "subject": _header(headers, "Subject")}
                )
                if len(top_subjects) >= _TOP_SUBJECTS_LIMIT:
                    break
    except HttpError as e:
        logger.error(f"Gmail API error: {e}", exc_info=True)
        _record_error(e)
        return None
    except Exception as e:
        logger.error(f"Unexpected error calling Gmail: {e}", exc_info=True)
        return None

    return {
        "unread_count": unread_count,
        # True when the real total is higher than unread_count, so the
        # brief can say "2000+" rather than stating a number it knows is
        # short.
        "unread_capped": unread_capped,
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
        # Over-fetch: bulk mail is dropped after the metadata fetch, so
        # asking for exactly `need` would return short whenever any of it
        # turned out to be a newsletter.
        msgs = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=(need * 3) + len(seen))
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
                    metadataHeaders=_BULK_HEADERS,
                )
                .execute()
            )
            headers = detail.get("payload", {}).get("headers", [])
            seen.add(msg["id"])
            # Marked seen BEFORE the bulk check, so a dropped message is
            # not re-fetched by the LATER pass below only to be dropped
            # again.
            if _is_bulk(headers):
                continue
            out.append(
                {"subject": _header(headers, "Subject") or "(no subject)", "from": _header(headers, "From")}
            )
        return out

    try:
        seen: set = set()
        urgent = _fetch(IMPORTANT_QUERY, limit, seen)
        for m in urgent:
            m["flag"] = "URGENT"
        later = _fetch(UNREAD_QUERY, limit - len(urgent), seen)
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
