"""Backfill what price did 5/10/20 trading days after each flagged setup.

Runs as part of the nightly job. For every setup with a missing forward
return whose horizon has now elapsed, computes the percent change from the
setup's close to the close N trading days later. This is what makes the
history view honest: hit rates come from realized outcomes, not from the
score that was assigned at the time.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import pandas as pd

from prices import download_history
from supabase_io import get_setups, update_setup

HORIZONS = (5, 10, 20)
log = logging.getLogger(__name__)


def _forward_return(closes: pd.Series, scan_day: date, days: int) -> float | None:
    """Percent change from the scan-day close to the close `days` bars later."""
    idx = closes.index.normalize()
    matches = idx[idx == pd.Timestamp(scan_day)]
    if len(matches) == 0:
        return None
    pos = int(idx.get_loc(matches[0]))
    target = pos + days
    if target >= len(closes):
        return None  # horizon hasn't elapsed yet
    base = float(closes.iloc[pos])
    if base <= 0:
        return None
    return round((float(closes.iloc[target]) / base - 1) * 100, 3)


def backfill_outcomes(lookback_days: int = 90) -> int:
    """Fill missing fwd_5d/10d/20d on recent setups. Returns rows updated."""
    since = (date.today() - timedelta(days=lookback_days)).isoformat()
    pending = get_setups(
        f"select=id,ticker,scan_date,fwd_5d,fwd_10d,fwd_20d"
        f"&scan_date=gte.{since}&fwd_20d=is.null&order=scan_date.asc&limit=5000"
    )
    if not pending:
        log.info("no setups pending outcome backfill")
        return 0

    by_ticker: dict[str, list[dict]] = {}
    for row in pending:
        by_ticker.setdefault(row["ticker"], []).append(row)
    log.info("backfilling outcomes for %d setups across %d tickers",
             len(pending), len(by_ticker))

    frames = download_history(sorted(by_ticker), period="6mo")
    updated = 0
    for ticker, rows in by_ticker.items():
        df = frames.get(ticker)
        if df is None or df.empty:
            continue
        closes = df["close"]
        for row in rows:
            scan_day = datetime.fromisoformat(row["scan_date"]).date()
            patch = {}
            for days in HORIZONS:
                field = f"fwd_{days}d"
                if row.get(field) is not None:
                    continue
                value = _forward_return(closes, scan_day, days)
                if value is not None:
                    patch[field] = value
            if patch:
                update_setup(row["id"], patch)
                updated += 1
    log.info("updated outcomes on %d setups", updated)
    return updated
