"""Unit tests for the core mechanics: costs, sessions, signals, sizing, and
engine fills on hand-crafted candles. Run with pytest, or directly:

    python -m pytest tests/ -q
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forex_backtester.config import (
    BacktestConfig, CostConfig, RiskConfig, SessionConfig, StrategyConfig,
)
from forex_backtester.engine.backtest import Backtester
from forex_backtester.engine.execution import CostModel
from forex_backtester.engine.risk import RiskManager
from forex_backtester.sessions import session_label
from forex_backtester.strategy.mean_reversion import BollingerFade

PIP = 0.0001
UTC = timezone.utc


def ts(h, m=0, day=6):
    # 2026-07-06 is a Monday.
    return datetime(2026, 7, day, h, m, tzinfo=UTC)


# -- cost model --------------------------------------------------------------

def test_entry_fill_pays_half_spread_plus_slippage():
    cm = CostModel(CostConfig(spread_pips=1.0, slippage_pips=0.5), PIP)
    mid = 1.10000
    assert cm.entry_fill(+1, mid) == pytest.approx(1.10010)  # +0.5 +0.5 pips
    assert cm.entry_fill(-1, mid) == pytest.approx(1.09990)


# -- sessions ----------------------------------------------------------------

def test_session_labels():
    cfg = SessionConfig()
    assert session_label(ts(8), cfg) == "london"
    assert session_label(ts(13), cfg) == "overlap"
    assert session_label(ts(18), cfg) == "newyork"
    assert session_label(ts(3), cfg) is None
    assert session_label(ts(22), cfg) is None
    assert session_label(datetime(2026, 7, 11, 13, tzinfo=UTC), cfg) is None  # Saturday


# -- risk --------------------------------------------------------------------

def test_position_sizing_risks_one_percent():
    rm = RiskManager(RiskConfig(initial_equity=100_000, risk_per_trade=0.01))
    # 1% of 100k = 1000 at risk; 20 pips * 0.0001 = 0.002 per unit -> 500k units
    # (notional 550k, under the 20x leverage cap of ~1.82M units).
    assert rm.units_for_trade(100_000, stop_pips=20, pip_size=PIP, price=1.10) == 500_000
    # A 2-pip stop would size to 5M units; the leverage cap binds instead.
    assert rm.units_for_trade(100_000, stop_pips=2, pip_size=PIP, price=1.10) == \
        int(100_000 * 20 / 1.10)


def test_daily_loss_cutoff_halts_entries():
    rm = RiskManager(RiskConfig(daily_loss_limit=0.03))
    rm.roll_day(ts(8), 100_000)
    rm.record_realized(-2_000)
    assert rm.can_open(0)
    rm.record_realized(-1_500)   # cumulative -3.5% of day-start equity
    assert not rm.can_open(0)
    rm.roll_day(ts(8, day=7), 96_500)  # next day resets the halt
    assert rm.can_open(0)


def test_max_positions():
    rm = RiskManager(RiskConfig(max_open_positions=3))
    rm.roll_day(ts(8), 100_000)
    assert rm.can_open(2)
    assert not rm.can_open(3)


# -- strategy ----------------------------------------------------------------

def _flat_then_spike(spike_pips: float, n_flat: int = 30) -> pd.DataFrame:
    """Flat closes with mild noise, then one bar closing spike_pips higher."""
    rng = np.random.default_rng(7)
    idx = pd.date_range(ts(9), periods=n_flat + 1, freq="5min", tz="UTC")
    close = 1.1000 + rng.normal(0, 1.5, n_flat + 1) * PIP
    close[-1] = 1.1000 + spike_pips * PIP
    df = pd.DataFrame({
        "open": close, "high": close + 0.5 * PIP,
        "low": close - 0.5 * PIP, "close": close, "volume": 100,
    }, index=idx)
    return df


def test_bollinger_fade_shorts_an_upside_spike():
    strat = BollingerFade(StrategyConfig())
    sig = strat.on_bar("EUR_USD", _flat_then_spike(spike_pips=12))
    assert sig is not None and sig.side == -1
    assert 8.0 <= sig.target_pips <= 15.0
    assert sig.stop_pips == pytest.approx(sig.target_pips * 1.5)


def test_bollinger_fade_skips_small_reversions():
    # A 4-pip spike breaches the tight bands of a near-flat series, but the
    # distance back to the mean is < 8 pips -> no trade.
    strat = BollingerFade(StrategyConfig())
    sig = strat.on_bar("EUR_USD", _flat_then_spike(spike_pips=4))
    assert sig is None


# -- engine fills ------------------------------------------------------------

def _engine_config() -> BacktestConfig:
    # Note bb_period=5 would be degenerate here: for a single spike after
    # constant closes, the band lands exactly on the spike close when
    # 1 + 2*sqrt(n-1) == n, which holds at n=5. Use 8.
    return BacktestConfig(
        strategy=StrategyConfig(bb_period=8, min_target_pips=8,
                                max_target_pips=15, stop_multiple=1.5),
        risk=RiskConfig(initial_equity=100_000),
    )


def _spike_and_revert() -> pd.DataFrame:
    """Warmup flat bars, a 12-pip up-spike, then a slide back down through
    any plausible take-profit."""
    closes = [1.1000] * 10 + [1.1012] + [1.1006, 1.0999, 1.0992, 1.0990, 1.0990]
    idx = pd.date_range(ts(9), periods=len(closes), freq="5min", tz="UTC")
    close = np.array(closes)
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + 0.2 * PIP
    low = np.minimum(open_, close) - 0.2 * PIP
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": 100},
        index=idx,
    )


def test_engine_short_fade_hits_target_with_costs():
    df = _spike_and_revert()
    cfg = _engine_config()
    result = Backtester(BollingerFade(cfg.strategy), cfg).run({"EUR_USD": df})
    assert len(result.trades) == 1
    t = result.trades.iloc[0]
    assert t["side"] == "short"
    assert t["exit_reason"] == "tp"
    # Entry at next bar open (1.1012 mid) minus half spread minus slippage.
    assert t["entry_price"] == pytest.approx(1.1012 - 1.0 * PIP)
    # Short TP is entry - target; profit in pips equals the target.
    assert t["pips"] == pytest.approx(t["target_pips"])
    assert t["pnl"] > 0
    assert result.final_equity == pytest.approx(100_000 + t["pnl"])


def test_engine_stop_is_hard_and_pays_slippage():
    # Spike up, then keep running up through the stop.
    closes = [1.1000] * 10 + [1.1012] + [1.1025, 1.1040, 1.1040, 1.1040]
    idx = pd.date_range(ts(9), periods=len(closes), freq="5min", tz="UTC")
    close = np.array(closes)
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + 0.2 * PIP
    low = np.minimum(open_, close) - 0.2 * PIP
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": 100},
        index=idx,
    )
    cfg = _engine_config()
    result = Backtester(BollingerFade(cfg.strategy), cfg).run({"EUR_USD": df})
    stop_outs = result.trades[result.trades["exit_reason"] == "sl"]
    assert len(stop_outs) >= 1
    t = stop_outs.iloc[0]
    assert t["pnl"] < 0
    # Loss is at least the planned stop distance (plus exit slippage); with a
    # 1%-risk position that is >= ~1% of equity but bounded by gap handling.
    assert -t["pnl"] >= t["units"] * t["stop_pips"] * PIP * 0.999


def test_portfolio_rules_hold_on_synthetic_data():
    """Interval-sweep audit of a two-instrument run: the position cap must
    hold in real time (entries at a bar open may not consume slots freed by
    exits later inside that same bar), entries stay inside sessions, and
    stop-outs risk ~1% of equity."""
    from forex_backtester.synthetic import generate_candles

    start = datetime(2026, 1, 5, tzinfo=UTC)
    end = datetime(2026, 3, 27, tzinfo=UTC)
    data = {
        inst: generate_candles(inst, start, end, 5, seed=i)
        for i, inst in enumerate(["EUR_USD", "GBP_USD"])
    }
    cfg = BacktestConfig()
    result = Backtester(BollingerFade(cfg.strategy), cfg).run(data)
    trades = result.trades
    assert len(trades) > 50

    # exits sort before entries at equal timestamps: a position exiting
    # within bar [t, t+5) is gone before an entry at the next bar's open t+5.
    events = sorted(
        [(t, 0) for t in trades["exit_time"]] + [(t, 1) for t in trades["entry_time"]]
    )
    concurrent = peak = 0
    for _, kind in events:
        concurrent += 1 if kind else -1
        peak = max(peak, concurrent)
    assert peak <= cfg.risk.max_open_positions

    hours = trades["entry_time"].dt.hour
    assert ((hours >= 7) & (hours < 21)).all()
    assert (trades["entry_time"].dt.weekday < 5).all()

    stops = trades[trades["exit_reason"] == "sl"]
    if len(stops):
        equity_before = stops["equity_after"] - stops["pnl"]
        risk_pct = -stops["pnl"] / equity_before
        # 1% planned risk plus exit slippage/gap tolerance.
        assert risk_pct.median() == pytest.approx(0.01, abs=0.002)


def test_no_entries_outside_sessions():
    # Same spike pattern but at 03:00 UTC (Asia hours) -> no trades.
    df = _spike_and_revert()
    df.index = pd.date_range(ts(3), periods=len(df), freq="5min", tz="UTC")
    cfg = _engine_config()
    result = Backtester(BollingerFade(cfg.strategy), cfg).run({"EUR_USD": df})
    assert result.trades.empty
