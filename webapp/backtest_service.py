"""Cached backtest powering the members' dashboard.

One shared run on synthetic candles (no OANDA key required on a fresh
deploy) is computed lazily on first use and cached in memory; every
subscriber view is a differently-gated slice of the same result. The
window is kept modest so the first dashboard hit stays fast.
"""
from __future__ import annotations

import io
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd

from forex_backtester.analysis.metrics import (
    compute_metrics, instrument_breakdown, session_breakdown,
)
from forex_backtester.analysis.plots import plot_equity_curve
from forex_backtester.config import BacktestConfig
from forex_backtester.engine.backtest import Backtester
from forex_backtester.strategy.mean_reversion import BollingerFade
from forex_backtester.synthetic import generate_candles

INSTRUMENTS = ["EUR_USD", "GBP_USD"]
GRANULARITY_MINUTES = 5
WINDOW_DAYS = 120
#: Fixed seed per instrument so every server restart shows the same run.
SEEDS = {"EUR_USD": 13, "GBP_USD": 17}


@dataclass
class DashboardData:
    metrics: dict
    sessions: pd.DataFrame
    instruments: pd.DataFrame
    trades: pd.DataFrame
    equity: pd.DataFrame
    initial_equity: float
    as_of: datetime
    window_days: int = WINDOW_DAYS

    def chart_png(self) -> bytes:
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "equity.png"
            plot_equity_curve(
                self.equity, self.initial_equity, out,
                title=f"Bollinger fade — {', '.join(INSTRUMENTS)} "
                      f"M{GRANULARITY_MINUTES}, last {self.window_days} days",
            )
            return out.read_bytes()

    def trades_csv(self) -> bytes:
        buf = io.StringIO()
        self.trades.to_csv(buf, index=False)
        return buf.getvalue().encode()


_cache: DashboardData | None = None
_lock = threading.Lock()


def get_dashboard_data() -> DashboardData:
    global _cache
    if _cache is not None:
        return _cache
    with _lock:
        if _cache is None:
            _cache = _run()
    return _cache


def _run() -> DashboardData:
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=WINDOW_DAYS)
    data = {
        inst: generate_candles(inst, start, end, GRANULARITY_MINUTES,
                               seed=SEEDS.get(inst))
        for inst in INSTRUMENTS
    }
    config = BacktestConfig()
    result = Backtester(BollingerFade(config.strategy), config).run(
        data, granularity_minutes=GRANULARITY_MINUTES
    )
    metrics = compute_metrics(result.trades, result.equity, result.initial_equity)
    return DashboardData(
        metrics=metrics,
        sessions=session_breakdown(result.trades),
        instruments=instrument_breakdown(result.trades),
        trades=result.trades,
        equity=result.equity,
        initial_equity=result.initial_equity,
        as_of=end,
    )
