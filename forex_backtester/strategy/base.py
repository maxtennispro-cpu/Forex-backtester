"""Strategy interface.

The contract that keeps strategies pluggable into a live engine:

* A strategy only ever sees **completed bars**. It never touches the account,
  the broker, position state, or the clock.
* It emits :class:`Signal` objects -- pure trade intents expressed in pips.
  Position sizing, session gating, risk limits, and order routing are the
  engine's job (backtest engine today, live engine later).

Two entry points are provided:

* ``compute_indicators`` + ``signal_for_bar`` -- the vectorised path the
  backtester uses (indicators precomputed over the whole frame, then one
  cheap check per bar).
* ``on_bar`` -- the incremental path a live engine would use: feed it a
  rolling window of the most recent completed bars, get back a signal or
  None. It is implemented on top of the same two methods, so both paths run
  identical logic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class Signal:
    """A trade intent. Distances are in pips, relative to the eventual fill."""

    instrument: str
    time: datetime          # open time of the bar that produced the signal
                            # (the signal itself is as of that bar's close)
    side: int               # +1 long, -1 short
    target_pips: float      # take-profit distance
    stop_pips: float        # hard-stop distance
    reason: str = ""


class Strategy(ABC):
    """Base class for bar-driven signal generators."""

    #: bars of history required before signals are valid
    warmup_bars: int = 0

    @abstractmethod
    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a copy of ``df`` (OHLC, UTC-indexed) with indicator columns
        added. Must be pure -- no state carried between calls."""

    @abstractmethod
    def signal_for_bar(
        self, instrument: str, bar: Any, bar_time: datetime
    ) -> Signal | None:
        """Evaluate one bar (a row of ``compute_indicators`` output, accessed
        by attribute) as of its close. Return a Signal or None."""

    def on_bar(self, instrument: str, history: pd.DataFrame) -> Signal | None:
        """Live-engine entry point.

        ``history`` is a window of completed bars (most recent last) at least
        ``warmup_bars + 1`` long. Runs the same code as the backtest path.
        """
        window = history.tail(self.warmup_bars + 1)
        if len(window) < self.warmup_bars + 1:
            return None
        enriched = self.compute_indicators(window)
        return self.signal_for_bar(instrument, enriched.iloc[-1], window.index[-1])
