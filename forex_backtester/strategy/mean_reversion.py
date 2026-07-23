"""Bollinger-band mean-reversion ("fade") strategy.

Setup: 20-period simple moving average with 2-standard-deviation bands on
5-minute closes. When a bar closes beyond a band -- i.e. the move has
extended 2+ standard deviations from the mean -- fade it: short a close
above the upper band, buy a close below the lower band.

Take-profit targets the reversion back toward the middle band, clamped to
the 8-15 pip window. If the middle band is closer than the minimum target,
the reversion on offer is too small to clear costs and the setup is skipped.
The hard stop is a fixed multiple of the target distance.

``require_band_cross`` restricts entries to the *first* close outside the
band (the previous close was still inside), so a sustained trend that rides
the band produces one fade, not one per bar.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from ..config import StrategyConfig, pip_size
from .base import Signal, Strategy


class BollingerFade(Strategy):
    def __init__(self, cfg: StrategyConfig | None = None):
        self.cfg = cfg or StrategyConfig()
        self.warmup_bars = self.cfg.bb_period + 1  # +1 for prev-bar columns

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        cfg = self.cfg
        out = df.copy()
        ma = out["close"].rolling(cfg.bb_period).mean()
        sd = out["close"].rolling(cfg.bb_period).std(ddof=0)
        out["bb_mid"] = ma
        out["bb_upper"] = ma + cfg.bb_std * sd
        out["bb_lower"] = ma - cfg.bb_std * sd
        out["prev_close"] = out["close"].shift(1)
        out["prev_upper"] = out["bb_upper"].shift(1)
        out["prev_lower"] = out["bb_lower"].shift(1)
        return out

    def signal_for_bar(
        self, instrument: str, bar: Any, bar_time: datetime
    ) -> Signal | None:
        cfg = self.cfg
        upper = bar.bb_upper
        lower = bar.bb_lower
        mid = bar.bb_mid
        if not np.isfinite(upper) or not np.isfinite(bar.prev_upper):
            return None  # still inside the warmup window

        close = bar.close
        pip = pip_size(instrument)

        if close > upper:
            if cfg.require_band_cross and bar.prev_close > bar.prev_upper:
                return None
            side = -1  # fade the up-move
        elif close < lower:
            if cfg.require_band_cross and bar.prev_close < bar.prev_lower:
                return None
            side = +1  # fade the down-move
        else:
            return None

        reversion_pips = abs(close - mid) / pip
        if reversion_pips < cfg.min_target_pips:
            return None
        target = min(reversion_pips, cfg.max_target_pips)
        return Signal(
            instrument=instrument,
            time=bar_time,
            side=side,
            target_pips=target,
            stop_pips=target * cfg.stop_multiple,
            reason=f"close {'above' if side < 0 else 'below'} {cfg.bb_std:g}sd band, "
                   f"{reversion_pips:.1f} pips from mean",
        )
