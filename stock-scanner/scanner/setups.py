"""Setup detection on the latest bar of an indicator-enriched frame.

Each detector looks only at the most recent row (and its immediate
history) and returns None or a dict describing the setup. `detect_setups`
runs all four and can flag multiple setups on the same ticker/day.
"""
from __future__ import annotations

import math

import pandas as pd

BREAKOUT_MIN_REL_VOLUME = 2.0
VOLUME_SPIKE_MIN_REL_VOLUME = 3.0
MOMENTUM_MACD_CROSS_MAX_DAYS = 3


def _last(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    return df.iloc[-1], df.iloc[-2]


def _clean(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def snapshot(row: pd.Series) -> dict:
    """The indicator values stored with a setup (and sent to the AI scorer)."""
    return {k: _clean(row.get(k)) for k in (
        "rsi", "macd", "macd_signal", "macd_hist", "days_since_macd_bull_cross",
        "sma20", "sma50", "sma200", "bb_percent_b", "rel_volume", "atr",
        "pct_from_52w_high", "range_high", "range_low", "range_width",
    )} | {
        "close": _clean(row.get("close")),
        "above_sma20": bool(row["close"] > row["sma20"]) if _clean(row.get("sma20")) else None,
        "above_sma50": bool(row["close"] > row["sma50"]) if _clean(row.get("sma50")) else None,
        "above_sma200": bool(row["close"] > row["sma200"]) if _clean(row.get("sma200")) else None,
    }


def breakout(df: pd.DataFrame) -> dict | None:
    """Close above a multi-week tight range on 2x+ average volume."""
    row, _ = _last(df)
    if not bool(row.get("in_consolidation")):
        return None
    if _clean(row.get("range_high")) is None or _clean(row.get("rel_volume")) is None:
        return None
    if row["close"] > row["range_high"] and row["rel_volume"] >= BREAKOUT_MIN_REL_VOLUME:
        return {"setup_type": "breakout"}
    return None


def volume_spike(df: pd.DataFrame) -> dict | None:
    """3x+ relative volume with a positive close."""
    row, prev = _last(df)
    rv = _clean(row.get("rel_volume"))
    if rv is not None and rv >= VOLUME_SPIKE_MIN_REL_VOLUME and row["close"] > prev["close"]:
        return {"setup_type": "volume_spike"}
    return None


def momentum(df: pd.DataFrame) -> dict | None:
    """RSI crossing up through 50 with a MACD bullish cross within 3 days."""
    row, prev = _last(df)
    crossed_50 = prev["rsi"] < 50 <= row["rsi"]
    days = _clean(row.get("days_since_macd_bull_cross"))
    if crossed_50 and days is not None and days <= MOMENTUM_MACD_CROSS_MAX_DAYS:
        return {"setup_type": "momentum"}
    return None


def oversold_bounce(df: pd.DataFrame) -> dict | None:
    """RSI under 30 with a reversal candle (green close in the upper half
    of the day's range)."""
    row, prev = _last(df)
    oversold = min(row["rsi"], prev["rsi"]) < 30
    day_range = row["high"] - row["low"]
    reversal = (
        row["close"] > row["open"]
        and day_range > 0
        and row["close"] >= row["low"] + 0.5 * day_range
    )
    if oversold and reversal:
        return {"setup_type": "oversold_bounce"}
    return None


DETECTORS = (breakout, volume_spike, momentum, oversold_bounce)


def detect_setups(ticker: str, df: pd.DataFrame) -> list[dict]:
    """Run all detectors on the latest bar; returns rows ready for storage."""
    if len(df) < 60:  # not enough history for stable indicators
        return []
    row = df.iloc[-1]
    found = []
    for detector in DETECTORS:
        hit = detector(df)
        if hit is None:
            continue
        found.append({
            "scan_date": df.index[-1].strftime("%Y-%m-%d"),
            "ticker": ticker,
            "setup_type": hit["setup_type"],
            "close": round(float(row["close"]), 4),
            "volume": int(row["volume"]),
            "indicators": snapshot(row),
            "closes": [round(float(c), 4) for c in df["close"].tail(60)],
        })
    return found
