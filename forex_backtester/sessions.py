"""London / New York session filtering.

Trades are only opened while London or New York is active. Each trade is
tagged with the session regime at entry so results can be broken down by
``london`` (London only), ``overlap`` (both open), and ``newyork`` (NY only).
"""
from __future__ import annotations

from datetime import datetime

from .config import SessionConfig


def session_label(ts: datetime, cfg: SessionConfig) -> str | None:
    """Return the session regime for a UTC timestamp, or None outside hours.

    Weekends return None regardless of hour (no bars should exist there
    anyway, but the synthetic generator and any bad data are guarded too).
    """
    if ts.weekday() >= 5:  # Saturday / Sunday
        return None
    h = ts.hour
    in_london = cfg.london_open <= h < cfg.london_close
    in_newyork = cfg.newyork_open <= h < cfg.newyork_close
    if in_london and in_newyork:
        return "overlap"
    if in_london:
        return "london"
    if in_newyork:
        return "newyork"
    return None


def in_session(ts: datetime, cfg: SessionConfig) -> bool:
    return session_label(ts, cfg) is not None
