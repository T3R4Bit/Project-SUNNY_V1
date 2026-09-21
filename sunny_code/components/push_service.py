"""Web Push: VAPID keys, the subscription store, and sending.

WHY PUSH AT ALL, GIVEN THE TAILNET-ONLY POSTURE
-----------------------------------------------
Telegram was rejected because message content would live on a third
party's servers. Web Push does not have that problem: payloads are
encrypted client-side under a key only the subscribing browser holds
(RFC 8291), so Apple's and Google's push services relay ciphertext they
cannot read. What they do learn is that *a* notification was sent, and
when -- metadata, not content. That is the trade, and it is a much
smaller one than handing over the messages themselves.

The subscription endpoint is the only outbound connection: nothing needs
to reach Sunny from outside the tailnet.

KEYS
----
A VAPID keypair identifies this server to the push service. It is
generated once and kept in `.vapid/` (gitignored, same posture as the
Google and Garmin tokens). Regenerating it invalidates every existing
subscription, because a subscription is bound to the public key it was
created with -- so this generates only when no key exists, never on a
whim.

EXPIRY IS NORMAL
----------------
Subscriptions die routinely: the browser rotates them, the user clears
site data, the OS drops them. The push service reports that as 404 or
410, and the only correct response is to delete the subscription. Treating
it as an error to retry would mean hammering a dead endpoint forever.
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from sunny_code.components.db_connection import closing_transaction
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

# Contact address in the VAPID claim. Push services want a way to reach
# the sender about a misbehaving application; a mailto is the convention.
VAPID_SUBJECT = "mailto:keatonstuff@gmail.com"


def _key_dir() -> Path:
    return get_settings().project_root / ".vapid"


def _db_path() -> Path:
    return get_settings().project_root / "sunny.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing_transaction(_connect()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                endpoint   TEXT PRIMARY KEY,
                p256dh     TEXT NOT NULL,
                auth       TEXT NOT NULL,
                label      TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


# --- keys -----------------------------------------------------------------

def ensure_keys() -> Optional[Dict[str, str]]:
    """Load the VAPID keypair, generating one on first use.

    Returns {"public": <urlsafe b64>, "private_path": <path>} or None if
    the libraries aren't installed. Never regenerates an existing key:
    every live subscription is bound to the public key it was made with,
    so a new key would silently break every device at once.
    """
    try:
        from py_vapid import Vapid01
    except ImportError:
        logger.warning("py_vapid not installed — push unavailable")
        return None

    key_dir = _key_dir()
    private_path = key_dir / "private_key.pem"
    public_path = key_dir / "public_key.txt"

    try:
        if private_path.exists() and public_path.exists():
            return {"public": public_path.read_text(encoding="utf-8").strip(),
                    "private_path": str(private_path)}

        key_dir.mkdir(parents=True, exist_ok=True)
        vapid = Vapid01()
        vapid.generate_keys()
        vapid.save_key(str(private_path))

        public = _public_key_b64(vapid)
        public_path.write_text(public, encoding="utf-8")
        try:
            private_path.chmod(0o600)
        except OSError:
            pass
        logger.info("Generated a new VAPID keypair")
        return {"public": public, "private_path": str(private_path)}
    except Exception as e:
        logger.error(f"VAPID key setup failed: {e}", exc_info=True)
        return None


def _public_key_b64(vapid) -> str:
    """The public key as the unpadded urlsafe base64 the Push API wants.

    Browsers reject a padded or standard-alphabet key with an opaque
    error, so the encoding is done explicitly rather than trusting a
    helper to have picked the right variant.
    """
    import base64
    from cryptography.hazmat.primitives import serialization

    raw = vapid.public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def public_key() -> Optional[str]:
    keys = ensure_keys()
    return keys["public"] if keys else None


def is_configured() -> bool:
    return public_key() is not None


# --- subscriptions --------------------------------------------------------

def add_subscription(subscription: Dict, label: str = "") -> bool:
    """Store a browser's push subscription.

    Keyed on endpoint, so re-subscribing the same browser updates rather
    than duplicating -- otherwise a reinstalled PWA would get every
    notification twice.
    """
    init_db()
    endpoint = (subscription or {}).get("endpoint")
    keys = (subscription or {}).get("keys") or {}
    if not endpoint or not keys.get("p256dh") or not keys.get("auth"):
        return False

    try:
        with closing_transaction(_connect()) as conn:
            conn.execute(
                """
                INSERT INTO push_subscriptions (endpoint, p256dh, auth, label, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(endpoint) DO UPDATE SET
                    p256dh = excluded.p256dh, auth = excluded.auth, label = excluded.label
                """,
                (endpoint, keys["p256dh"], keys["auth"], label[:80], datetime.now().isoformat(timespec="seconds")),
            )
        logger.info(f"Push subscription stored ({label or 'unlabelled'})")
        return True
    except sqlite3.Error as e:
        logger.error(f"Could not store push subscription: {e}", exc_info=True)
        return False


def remove_subscription(endpoint: str) -> bool:
    init_db()
    try:
        with closing_transaction(_connect()) as conn:
            conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
        return True
    except sqlite3.Error as e:
        logger.error(f"Could not remove push subscription: {e}", exc_info=True)
        return False


def list_subscriptions() -> List[Dict]:
    init_db()
    try:
        with closing_transaction(_connect()) as conn:
            rows = conn.execute(
                "SELECT endpoint, p256dh, auth, label, created_at FROM push_subscriptions"
            ).fetchall()
    except sqlite3.Error as e:
        logger.error(f"Could not list push subscriptions: {e}", exc_info=True)
        return []
    return [dict(r) for r in rows]


def subscription_count() -> int:
    return len(list_subscriptions())


# --- sending --------------------------------------------------------------

def send(title: str, body: str = "", url: str = "/sunny", tag: str = "sunny",
         require_interaction: bool = False) -> Dict:
    """Push a notification to every subscribed device.

    Synchronous and blocking -- callers should run it off the event loop
    (asyncio.to_thread). Returns a summary rather than raising: a
    notification failing must never take down the thing that triggered it.
    """
    keys = ensure_keys()
    if keys is None:
        return {"ok": False, "reason": "no_keys", "sent": 0, "removed": 0}

    subscriptions = list_subscriptions()
    if not subscriptions:
        return {"ok": True, "reason": "no_subscribers", "sent": 0, "removed": 0}

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.warning("pywebpush not installed — push unavailable")
        return {"ok": False, "reason": "not_installed", "sent": 0, "removed": 0}

    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "tag": tag,
        "require_interaction": require_interaction,
    })

    sent, removed = 0, 0
    for sub in subscriptions:
        info = {
            "endpoint": sub["endpoint"],
            "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
        }
        try:
            webpush(
                subscription_info=info,
                data=payload,
                vapid_private_key=keys["private_path"],
                vapid_claims={"sub": VAPID_SUBJECT},
                timeout=10,
            )
            sent += 1
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                # Gone for good -- the browser rotated it, the user
                # cleared site data, or the OS dropped it. Deleting is the
                # only correct response; retrying would hammer a dead
                # endpoint forever.
                remove_subscription(sub["endpoint"])
                removed += 1
                logger.info(f"Pruned expired push subscription (HTTP {status})")
            else:
                logger.warning(f"Push failed (HTTP {status}): {e}")
        except Exception as e:
            logger.error(f"Unexpected push failure: {e}", exc_info=True)

    return {"ok": True, "reason": None, "sent": sent, "removed": removed}
