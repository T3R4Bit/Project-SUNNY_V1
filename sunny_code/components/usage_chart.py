"""Renders a PNG chart of daily Claude API spend for the /usage Discord
command — the one clearly paid API in this app (see token_tracker.py's own
docstring: OpenWeatherMap/Google Calendar/Gmail are free-tier, Discord is
free). One series, one axis (daily cost) per the project's dataviz
guidance -- token count is real but a different scale, so it's shown as
text in the subtitle instead of a second y-axis, not plotted alongside cost.

Colors are the dataviz skill's validated dark-mode reference palette
(references/palette.md) -- rendered dark-surface-first (not just dark-
friendly) since this is always viewed as a Discord image attachment,
which sits on Discord's own dark theme for most viewers.
"""

import io
import logging
from typing import List

from sunny_code.components import token_tracker
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

_SURFACE = "#1a1a19"
_INK_PRIMARY = "#ffffff"
_INK_SECONDARY = "#c3c2b7"
_INK_MUTED = "#898781"
_GRIDLINE = "#2c2c2a"
_AXIS = "#383835"
_BAR = "#3987e5"  # sequential blue, step 400 -- single series, no legend needed
_CAP_LINE = "#898781"


def render_usage_chart_png(days: int = 30) -> bytes:
    """Daily Claude API cost, last `days` days, as a PNG. Never raises on
    empty data (renders a real chart with all-zero bars rather than
    erroring) -- callers should still guard against matplotlib itself
    being unavailable if that matters to them (it's a real dependency,
    not optional)."""
    import matplotlib
    matplotlib.use("Agg")  # headless -- no display, no GUI backend needed
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import date as date_cls

    rows = token_tracker.get_daily_costs(days)
    dates = [date_cls.fromisoformat(r["date"]) for r in rows]
    costs = [r["cost"] for r in rows]
    total_cost = sum(costs)
    total_tokens = sum(r["total_tokens"] for r in rows)

    fig, ax = plt.subplots(figsize=(9, 4.2), dpi=150)
    fig.patch.set_facecolor(_SURFACE)
    ax.set_facecolor(_SURFACE)

    ax.bar(dates, costs, width=0.7, color=_BAR, edgecolor=_SURFACE, linewidth=1.5, zorder=3)

    # The cap line is context, not the point of the chart -- real daily
    # spend on a personal assistant is normally a small fraction of the
    # configured cap, and letting axhline() autoscale the axis up to it
    # flattens every real bar into an invisible sliver (seen live while
    # building this). Only draw it when it's in the same neighborhood as
    # the actual data; otherwise just state it in the subtitle instead.
    settings = get_settings()
    daily_cap = getattr(settings, "daily_spend_cap", None)
    max_cost = max(costs) if costs else 0.0
    cap_line_drawn = False
    if daily_cap and max_cost > 0 and daily_cap <= max_cost * 3:
        ax.axhline(daily_cap, color=_CAP_LINE, linewidth=1, linestyle=(0, (4, 3)), zorder=2)
        # Escaped \$ -- an unescaped "$...$" pair anywhere in a matplotlib
        # text string is parsed as LaTeX mathtext, not a literal dollar
        # sign (confirmed live: the subtitle below rendered as raw math
        # markup before this fix).
        ax.text(
            dates[0], daily_cap, f" daily cap \\${daily_cap:.2f}",
            color=_INK_MUTED, fontsize=8, va="bottom", ha="left",
        )
        cap_line_drawn = True
    ax.set_ylim(0, max(max_cost, daily_cap if (daily_cap and cap_line_drawn) else 0) * 1.25 or 1.0)

    cap_note = "" if not daily_cap else f" (cap \\${daily_cap:.2f}/day)" if not cap_line_drawn else ""
    fig.text(0.045, 0.94, "Claude API — Daily Cost", color=_INK_PRIMARY, fontsize=15, ha="left", va="bottom")
    fig.text(
        0.045, 0.905,
        f"Last {days} days: \\${total_cost:.2f} total · {total_tokens:,} tokens{cap_note}",
        color=_INK_SECONDARY, fontsize=10, ha="left", va="top",
    )
    fig.subplots_adjust(top=0.82)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(_AXIS)

    ax.yaxis.grid(True, color=_GRIDLINE, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", colors=_INK_MUTED, labelsize=9, length=0)

    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=8))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    # Decimal places adapt to the axis scale -- a fixed 2 decimals looks
    # like duplicate labels ($0.01, $0.01, $0.01...) whenever the whole
    # range is a few cents (seen live on a near-idle day), since
    # consecutive ticks round to the same string at that precision.
    axis_top = ax.get_ylim()[1]
    decimals = 2 if axis_top >= 1 else (4 if axis_top < 0.1 else 3)
    ax.yaxis.set_major_formatter(lambda v, _pos: f"${v:.{decimals}f}" if v else "$0")

    fig.subplots_adjust(left=0.09, right=0.97, bottom=0.12)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=_SURFACE)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()
