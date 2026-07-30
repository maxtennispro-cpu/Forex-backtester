"""Technical indicators on a daily OHLCV frame.

Input frames use lowercase columns: open, high, low, close, volume, with a
DatetimeIndex in ascending order. Every function is pure and vectorized;
`compute_all` returns the frame with indicator columns appended.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RSI_PERIOD = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
BB_PERIOD, BB_STD = 20, 2.0
ATR_PERIOD = 14
REL_VOLUME_DAYS = 30
CONSOLIDATION_DAYS = 20          # range window checked just before today
CONSOLIDATION_MAX_WIDTH = 0.08   # (high-low)/low of the window, <= 8% = "tight"


def rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """Wilder's RSI.

    With no losses in the window RSI is 100 (and 0 with no gains); only a
    completely flat series is neutral. Dividing by a zeroed loss average
    would give NaN, so those cases are filled explicitly rather than being
    collapsed to 50.
    """
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    out = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    out = out.mask((loss == 0) & (gain > 0), 100.0)
    out = out.mask((gain == 0) & (loss > 0), 0.0)
    return out.mask((gain == 0) & (loss == 0), 50.0).fillna(50.0)


def macd(close: pd.Series) -> pd.DataFrame:
    fast = close.ewm(span=MACD_FAST, adjust=False).mean()
    slow = close.ewm(span=MACD_SLOW, adjust=False).mean()
    line = fast - slow
    signal = line.ewm(span=MACD_SIGNAL, adjust=False).mean()
    return pd.DataFrame({"macd": line, "macd_signal": signal,
                         "macd_hist": line - signal})


def atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    close = out["close"]

    out["rsi"] = rsi(close)
    out = out.join(macd(close))
    # Days since the most recent bullish MACD cross (line crossing above signal).
    bull_cross = (out["macd"] > out["macd_signal"]) & \
                 (out["macd"].shift(1) <= out["macd_signal"].shift(1))
    last_cross = pd.Series(np.where(bull_cross, np.arange(len(out)), np.nan),
                           index=out.index).ffill()
    out["days_since_macd_bull_cross"] = np.arange(len(out)) - last_cross

    for n in (20, 50, 200):
        out[f"sma{n}"] = close.rolling(n).mean()

    mid = close.rolling(BB_PERIOD).mean()
    sd = close.rolling(BB_PERIOD).std(ddof=0)
    out["bb_upper"] = mid + BB_STD * sd
    out["bb_lower"] = mid - BB_STD * sd
    width = (out["bb_upper"] - out["bb_lower"])
    out["bb_percent_b"] = (close - out["bb_lower"]) / width.replace(0, np.nan)

    out["atr"] = atr(out)
    # Today's volume against the average of the *prior* 30 sessions — including
    # today would dilute the very spike being measured.
    prior_volume = out["volume"].shift(1).rolling(REL_VOLUME_DAYS).mean()
    out["rel_volume"] = out["volume"] / prior_volume.replace(0, np.nan)

    out["high_52w"] = out["high"].rolling(252, min_periods=60).max()
    out["pct_from_52w_high"] = close / out["high_52w"] - 1

    # Consolidation range over the window ending *yesterday* (so a breakout
    # bar doesn't inflate its own range).
    range_high = out["high"].shift(1).rolling(CONSOLIDATION_DAYS).max()
    range_low = out["low"].shift(1).rolling(CONSOLIDATION_DAYS).min()
    out["range_high"] = range_high
    out["range_low"] = range_low
    out["range_width"] = (range_high - range_low) / range_low.replace(0, np.nan)
    out["in_consolidation"] = out["range_width"] <= CONSOLIDATION_MAX_WIDTH
    return out
