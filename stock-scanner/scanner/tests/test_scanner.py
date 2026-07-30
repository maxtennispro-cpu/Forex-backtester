"""Tests for indicators and setup detection.

Frames are synthesized to trigger (or deliberately not trigger) each
setup, so the detectors are tested against known-shape price action
rather than whatever the market happened to do.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from indicators import compute_all, rsi, macd, atr
from setups import (breakout, detect_setups, momentum, oversold_bounce,
                    snapshot, volume_spike)


def make_frame(closes, volumes=None, highs=None, lows=None, opens=None) -> pd.DataFrame:
    n = len(closes)
    closes = np.asarray(closes, dtype=float)
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    return pd.DataFrame({
        "open": np.asarray(opens, dtype=float) if opens is not None else closes,
        "high": np.asarray(highs, dtype=float) if highs is not None else closes * 1.005,
        "low": np.asarray(lows, dtype=float) if lows is not None else closes * 0.995,
        "close": closes,
        "volume": np.asarray(volumes, dtype=float) if volumes is not None
                  else np.full(n, 1_000_000.0),
    }, index=idx)


# --------------------------------------------------------------------------
# Indicators
# --------------------------------------------------------------------------

def test_rsi_bounds_and_direction():
    up = rsi(pd.Series(np.linspace(100, 200, 100)))
    down = rsi(pd.Series(np.linspace(200, 100, 100)))
    assert up.iloc[-1] > 90            # relentless uptrend -> RSI pinned high
    assert down.iloc[-1] < 10
    assert ((up >= 0) & (up <= 100)).all()


def test_rsi_flat_series_is_neutral():
    flat = rsi(pd.Series([50.0] * 60))
    assert 45 <= flat.iloc[-1] <= 55


def test_macd_cross_detected_on_trend_reversal():
    closes = np.concatenate([np.linspace(100, 80, 60), np.linspace(80, 110, 40)])
    out = macd(pd.Series(closes))
    assert out["macd"].iloc[-1] > out["macd_signal"].iloc[-1]  # bullish after reversal


def test_atr_positive_and_tracks_range():
    tight = make_frame([100] * 60)
    wide = make_frame([100] * 60, highs=[110] * 60, lows=[90] * 60)
    assert atr(tight).iloc[-1] < atr(wide).iloc[-1]
    assert atr(wide).iloc[-1] > 0


def test_compute_all_adds_expected_columns():
    df = compute_all(make_frame(np.linspace(100, 140, 300)))
    for col in ("rsi", "macd", "sma20", "sma50", "sma200", "bb_upper",
                "bb_percent_b", "atr", "rel_volume", "pct_from_52w_high",
                "range_high", "in_consolidation"):
        assert col in df.columns, col
    assert df["pct_from_52w_high"].iloc[-1] <= 0  # can't close above own 52w high


def test_relative_volume_reflects_spike():
    volumes = [1_000_000.0] * 59 + [4_000_000.0]
    df = compute_all(make_frame([100.0] * 60, volumes=volumes))
    assert df["rel_volume"].iloc[-1] == pytest.approx(4.0, rel=0.05)


# --------------------------------------------------------------------------
# Setup detectors
# --------------------------------------------------------------------------

def test_breakout_fires_on_range_break_with_volume():
    closes = [100.0] * 59 + [106.0]        # tight range then a break
    volumes = [1_000_000.0] * 59 + [3_000_000.0]
    df = compute_all(make_frame(closes, volumes=volumes))
    assert breakout(df) == {"setup_type": "breakout"}


def test_breakout_requires_volume_confirmation():
    closes = [100.0] * 59 + [106.0]
    df = compute_all(make_frame(closes))       # flat volume
    assert breakout(df) is None


def test_breakout_requires_prior_consolidation():
    closes = list(np.linspace(60, 140, 59)) + [150.0]   # wide, trending range
    volumes = [1_000_000.0] * 59 + [5_000_000.0]
    df = compute_all(make_frame(closes, volumes=volumes))
    assert breakout(df) is None


def test_volume_spike_needs_positive_close():
    volumes = [1_000_000.0] * 59 + [4_000_000.0]
    up = compute_all(make_frame([100.0] * 59 + [102.0], volumes=volumes))
    down = compute_all(make_frame([100.0] * 59 + [98.0], volumes=volumes))
    assert volume_spike(up) == {"setup_type": "volume_spike"}
    assert volume_spike(down) is None


def test_momentum_fires_on_rsi_50_cross_with_macd():
    # Flat base, a shallow 10% pullback, then a brisk four-day recovery. A
    # deeper selloff would push the MACD cross well ahead of the RSI-50
    # cross; this shape lands them a day apart, which is the setup.
    closes = [100.0] * 40 + list(np.linspace(100, 90, 25))
    price = closes[-1]
    for _ in range(4):
        price *= 1.012
        closes.append(price)
    df = compute_all(make_frame(closes))
    row, prev = df.iloc[-1], df.iloc[-2]
    assert prev["rsi"] < 50 <= row["rsi"], "fixture should straddle RSI 50"
    assert row["days_since_macd_bull_cross"] <= 3
    assert momentum(df) == {"setup_type": "momentum"}


def test_momentum_ignores_stale_macd_cross():
    closes = list(np.linspace(120, 90, 40)) + list(np.linspace(90, 130, 60))
    df = compute_all(make_frame(closes))
    assert momentum(df) is None      # RSI crossed 50 long ago, not on this bar


def test_oversold_bounce_requires_reversal_candle():
    closes = list(np.linspace(200, 100, 79))
    reversal_closes = closes + [104.0]
    df = compute_all(make_frame(
        reversal_closes,
        opens=closes + [100.5], highs=[c * 1.005 for c in closes] + [105.0],
        lows=[c * 0.995 for c in closes] + [99.0],
    ))
    assert df.iloc[-1]["rsi"] < 30 or df.iloc[-2]["rsi"] < 30
    assert oversold_bounce(df) == {"setup_type": "oversold_bounce"}


def test_oversold_bounce_ignores_continued_selling():
    closes = list(np.linspace(200, 100, 80))
    df = compute_all(make_frame(
        closes, opens=[c * 1.01 for c in closes],      # red candles throughout
        highs=[c * 1.02 for c in closes], lows=[c * 0.98 for c in closes],
    ))
    assert oversold_bounce(df) is None


# --------------------------------------------------------------------------
# Row assembly
# --------------------------------------------------------------------------

def test_detect_setups_builds_storable_rows():
    volumes = [1_000_000.0] * 59 + [4_000_000.0]
    df = compute_all(make_frame([100.0] * 59 + [106.0], volumes=volumes))
    rows = detect_setups("TEST", df)
    assert rows, "expected at least one setup"
    row = rows[0]
    assert row["ticker"] == "TEST"
    assert row["scan_date"] == df.index[-1].strftime("%Y-%m-%d")
    assert isinstance(row["volume"], int)
    assert len(row["closes"]) == 60
    assert {"breakout", "volume_spike"} & {r["setup_type"] for r in rows}


def test_detect_setups_skips_short_history():
    df = compute_all(make_frame([100.0] * 30))
    assert detect_setups("TEST", df) == []


def test_snapshot_is_json_safe():
    df = compute_all(make_frame([100.0] * 60))   # sma200 is NaN with 60 bars
    snap = snapshot(df.iloc[-1])
    assert snap["sma200"] is None
    for key, value in snap.items():
        assert value is None or isinstance(value, (int, float, bool)), key
