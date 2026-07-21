"""Synthetic 5-minute candle generator.

Used to smoke-test the full pipeline without OANDA credentials
(``run_backtest.py --synthetic``). Prices follow a mean-reverting
(Ornstein-Uhlenbeck-style) walk in log space with higher volatility during
London/NY hours, on a weekday-only 5-minute grid. It is *not* a market
model -- results on it prove the plumbing, not the strategy.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .config import SessionConfig
from .sessions import in_session

BASE_PRICES = {"EUR_USD": 1.08, "GBP_USD": 1.27}


def _trading_grid(start: datetime, end: datetime, minutes: int) -> pd.DatetimeIndex:
    idx = pd.date_range(start, end, freq=f"{minutes}min", tz="UTC", inclusive="left")
    # Approximate the FX week: closed Fri 21:00 UTC through Sun 21:00 UTC.
    dow, hour = idx.dayofweek, idx.hour
    closed = (
        (dow == 5)
        | ((dow == 4) & (hour >= 21))
        | ((dow == 6) & (hour < 21))
    )
    return idx[~closed]


def generate_candles(
    instrument: str,
    start: datetime,
    end: datetime,
    granularity_minutes: int = 5,
    seed: int | None = None,
) -> pd.DataFrame:
    rng = np.random.default_rng(
        seed if seed is not None else abs(hash(instrument)) % (2**32)
    )
    idx = _trading_grid(start, end, granularity_minutes)
    n = len(idx)
    base = BASE_PRICES.get(instrument, 1.0)
    scfg = SessionConfig()

    # Per-bar log-return vol: ~4.5 pips in session, ~1.8 pips off session.
    active = np.array([in_session(t, scfg) for t in idx])
    sigma = np.where(active, 4.5e-4, 1.8e-4)

    kappa = 0.01           # pull toward the slow-moving mean
    x = np.empty(n)
    x[0] = 0.0
    eps = rng.standard_normal(n)
    slow_mean = 0.0
    for i in range(1, n):
        slow_mean += 0.02 * (x[i - 1] - slow_mean)   # drifting anchor
        x[i] = x[i - 1] + kappa * (slow_mean - x[i - 1]) + sigma[i] * eps[i]

    close = base * np.exp(x)
    open_ = np.concatenate([[base], close[:-1]])
    wick = np.abs(rng.standard_normal((n, 2))) * sigma[:, None] * base * 0.8
    high = np.maximum(open_, close) + wick[:, 0]
    low = np.minimum(open_, close) - wick[:, 1]
    volume = rng.integers(50, 500, n)

    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )
    df.index.name = "time"
    return df
