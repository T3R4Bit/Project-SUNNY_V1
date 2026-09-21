"""Channel-agnostic outbound notification.

WHY THIS EXISTS
---------------
Due alarms and reminders were dispatched from inside discord_bot.py's
scheduled_check_loop. That had two consequences worth stating plainly:

  1. With Discord unconfigured, the loop never started, so a reminder
     created from the web or the Pi would never fire anywhere. The only
     "sounding" mechanism was a Discord message.
  2. The loop returned early when the channel could not be fetched --
     before marking anything fired or rescheduled -- so a permissions
     problem silently suppressed reminders rather than reporting one.

Delivery is now a fan-out: the scheduler asks notify.send() for a thing
to be delivered, and each registered channel does what it can. Discord is
one channel, Web Push is another, and neither is load-bearing for the
others. Adding SMS or a desk device later is a register() call, not
another branch in a loop that already does too much.

FAILURE POLICY
--------------
Every channel is attempted, and one failing never stops the rest. A
notification that cannot be delivered is logged, not raised -- the
scheduler must still mark the item fired, or it would re-fire forever.
"""

import asyncio
import logging
from typing import Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# An async callable taking (title, body). Registered by whatever owns the
# transport -- main.py wires Discord in when the bot exists.
Channel = Callable[[str, str], Awaitable[None]]

_channels: Dict[str, Channel] = {}


def register(name: str, channel: Optional[Channel]) -> None:
    """Add or replace a delivery channel. Passing None removes it, which
    is how main.py expresses "Discord isn't configured" without the
    caller needing to know why."""
    if channel is None:
        _channels.pop(name, None)
        return
    _channels[name] = channel
    logger.info(f"Notification channel registered: {name}")


def registered() -> List[str]:
    names = sorted(_channels)
    # push_service is not a registered callable -- it has no transport to
    # own and is always available when keys and subscribers exist -- so it
    # is reported here rather than in _channels.
    from sunny_code.components import push_service

    if push_service.is_configured() and push_service.subscription_count():
        names.append("push")
    return names


async def send(
    title: str,
    body: str = "",
    url: str = "/sunny",
    tag: str = "sunny",
    require_interaction: bool = False,
    channels: Optional[List[str]] = None,
) -> Dict:
    """Deliver a notification everywhere.

    `channels` restricts delivery to named registered channels; omitted
    means all of them plus push. `url`, `tag` and `require_interaction`
    only mean anything to push, and are ignored by channels that have no
    equivalent rather than being rejected.
    """
    from sunny_code.components import push_service

    results: Dict[str, object] = {}
    text = f"{title}: {body}" if body else title

    for name, channel in list(_channels.items()):
        if channels is not None and name not in channels:
            continue
        try:
            await channel(title, body)
            results[name] = "sent"
        except Exception as e:
            # One channel failing must not cost the others, and must not
            # stop the scheduler marking the item fired.
            logger.error(f"Notification channel {name!r} failed: {e}", exc_info=True)
            results[name] = f"failed: {type(e).__name__}"

    if channels is None or "push" in channels:
        try:
            # Blocking HTTP per subscriber -- off the event loop.
            results["push"] = await asyncio.to_thread(
                push_service.send, title, body, url, tag, require_interaction
            )
        except Exception as e:
            logger.error(f"Push notification failed: {e}", exc_info=True)
            results["push"] = f"failed: {type(e).__name__}"

    logger.info(f"Notified ({text[:60]}): {results}")
    return results
