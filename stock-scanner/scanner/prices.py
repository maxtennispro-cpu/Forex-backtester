"""End-of-day OHLCV download via yfinance.

Tickers are fetched in batches with `yf.download(..., group_by="ticker")`,
which is one HTTP request per batch rather than per symbol. Frames come
back with lowercase columns and a tz-naive ascending DatetimeIndex, which
is what `indicators` and `setups` expect.
"""
from __future__ import annotations

import logging

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

BATCH_SIZE = 100
COLUMNS = ["open", "high", "low", "close", "volume"]


def _tidy(df: pd.DataFrame) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    out = df.rename(columns=str.lower)
    missing = [c for c in COLUMNS if c not in out.columns]
    if missing:
        return None
    out = out[COLUMNS].dropna(subset=["close", "volume"])
    if out.empty:
        return None
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_localize(None)
    return out.sort_index()


def download_history(tickers: list[str], period: str = "2y") -> dict[str, pd.DataFrame]:
    """Download daily bars for many tickers. Failures are skipped, not fatal."""
    frames: dict[str, pd.DataFrame] = {}
    for start in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[start:start + BATCH_SIZE]
        log.info("downloading %d tickers (%d-%d of %d)",
                 len(batch), start + 1, start + len(batch), len(tickers))
        try:
            raw = yf.download(
                batch, period=period, interval="1d", group_by="ticker",
                auto_adjust=True, threads=True, progress=False,
            )
        except Exception as exc:
            log.warning("batch download failed, skipping: %s", exc)
            continue
        if raw is None or raw.empty:
            continue
        for ticker in batch:
            try:
                sub = raw[ticker] if isinstance(raw.columns, pd.MultiIndex) else raw
            except KeyError:
                continue
            tidy = _tidy(sub)
            if tidy is not None:
                frames[ticker] = tidy
    log.info("resolved price history for %d/%d tickers", len(frames), len(tickers))
    return frames
