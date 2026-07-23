"""Portfolio-level backtest engine.

Event model
-----------
Bars from all instruments are merged into one time-ordered stream (the risk
rules -- max open positions, daily loss cutoff -- are portfolio-wide, so the
instruments cannot be simulated independently). Candle timestamps are OANDA
convention: the bar's *open* time; a 5-minute bar stamped 12:00 closes at
12:05.

Per timestamp (all instruments' bars sharing an open time are one group), in
order:

1. **Fill pending entries** -- a signal produced on the previous bar's close
   is executed as a market order at this bar's open, provided the entry time
   is still inside a trading session and the risk manager allows a new
   position. Unfilled signals do not linger: they are good for exactly one
   bar. Entries for the whole group are filled before any exits are
   processed: an entry at the bar *open* must count positions that will exit
   later *within* the bar as still open, otherwise the position cap can be
   breached in real time.
2. **Check exits** for open positions. Stops are evaluated before targets
   (worst-case assumption when both levels are inside one bar's range).
   Triggers use reconstructed bid/ask, stops pay slippage, and adverse
   opening gaps fill at the gapped price rather than the stop level.
3. **Generate signals** from the bar closes (session-gated) to be filled at
   the next bar's open.

Equity is marked to market on mid closes at every bar. At the end of the
data any open positions are closed at the final mid close with full market
exit costs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable

import numpy as np
import pandas as pd

from ..config import BacktestConfig, pip_size
from ..sessions import session_label
from ..strategy.base import Signal, Strategy
from .execution import CostModel
from .risk import RiskManager


@dataclass
class Position:
    instrument: str
    side: int                # +1 long, -1 short
    units: int
    entry_time: datetime
    entry_price: float
    tp: float                # take-profit price
    sl: float                # hard-stop price
    target_pips: float
    stop_pips: float
    session: str
    signal_time: datetime


@dataclass
class Trade:
    instrument: str
    side: str                # "long" / "short"
    units: int
    signal_time: datetime
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    pnl: float
    pips: float
    target_pips: float
    stop_pips: float
    session: str
    exit_reason: str         # "tp" / "sl" / "end_of_data"
    equity_after: float


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    equity: pd.DataFrame     # index: bar open time; columns: equity (MTM), realized
    initial_equity: float
    config: BacktestConfig

    @property
    def final_equity(self) -> float:
        return float(self.equity["equity"].iloc[-1]) if len(self.equity) else self.initial_equity


class Backtester:
    def __init__(self, strategy: Strategy, config: BacktestConfig | None = None):
        self.strategy = strategy
        self.config = config or BacktestConfig()

    def run(self, data: dict[str, pd.DataFrame], granularity_minutes: int = 5) -> BacktestResult:
        cfg = self.config
        step = timedelta(minutes=granularity_minutes)
        risk = RiskManager(cfg.risk)
        cost_models = {
            inst: CostModel(cfg.costs, pip_size(inst)) for inst in data
        }

        # Vectorised indicator pass per instrument, then one merged stream.
        frames = []
        for inst, df in data.items():
            enriched = self.strategy.compute_indicators(df)
            enriched["instrument"] = inst
            frames.append(enriched)
        merged = pd.concat(frames).sort_index(kind="mergesort")

        equity = cfg.risk.initial_equity          # realized
        positions: list[Position] = []
        pending: dict[str, Signal] = {}           # instrument -> signal awaiting fill
        last_close: dict[str, float] = {}
        trades: list[Trade] = []
        eq_times: list[datetime] = []
        eq_mtm: list[float] = []
        eq_realized: list[float] = []

        def close_position(pos: Position, exit_time: datetime, exit_price: float,
                           reason: str) -> None:
            nonlocal equity
            pnl = (exit_price - pos.entry_price) * pos.side * pos.units
            equity += pnl
            risk.record_realized(pnl)
            trades.append(Trade(
                instrument=pos.instrument,
                side="long" if pos.side > 0 else "short",
                units=pos.units,
                signal_time=pos.signal_time,
                entry_time=pos.entry_time,
                exit_time=exit_time,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                pnl=pnl,
                pips=(exit_price - pos.entry_price) * pos.side / pip_size(pos.instrument),
                target_pips=pos.target_pips,
                stop_pips=pos.stop_pips,
                session=pos.session,
                exit_reason=reason,
                equity_after=equity,
            ))

        rows = list(merged.itertuples())
        i, n = 0, len(rows)
        while i < n:
            bar_time: datetime = rows[i].Index
            group = [rows[i]]
            while i + 1 < n and rows[i + 1].Index == bar_time:
                i += 1
                group.append(rows[i])
            i += 1
            bar_close_time = bar_time + step

            risk.roll_day(bar_time, equity)

            # 1. Fill pending entries (signals from the previous bar) at the
            # open -- for every instrument in the group, before any exits.
            for row in group:
                inst = row.instrument
                sig = pending.pop(inst, None)
                if sig is None:
                    continue
                entry_session = session_label(bar_time, cfg.sessions)
                if entry_session is None or not risk.can_open(len(positions)):
                    continue
                cm = cost_models[inst]
                fill = cm.entry_fill(sig.side, row.open)
                units = risk.units_for_trade(equity, sig.stop_pips, cm.pip_size, fill)
                if units > 0:
                    positions.append(Position(
                        instrument=inst,
                        side=sig.side,
                        units=units,
                        entry_time=bar_time,
                        entry_price=fill,
                        tp=fill + sig.side * sig.target_pips * cm.pip_size,
                        sl=fill - sig.side * sig.stop_pips * cm.pip_size,
                        target_pips=sig.target_pips,
                        stop_pips=sig.stop_pips,
                        session=entry_session,
                        signal_time=sig.time,
                    ))

            # 2. Exit checks (stop before target on ambiguous bars).
            bars = {row.instrument: row for row in group}
            still_open: list[Position] = []
            for pos in positions:
                row = bars.get(pos.instrument)
                if row is None:
                    still_open.append(pos)
                    continue
                cm = cost_models[pos.instrument]
                if pos.side > 0:
                    # Long exits on the bid.
                    bid_open, bid_low, bid_high = cm.bid(row.open), cm.bid(row.low), cm.bid(row.high)
                    if bid_low <= pos.sl:
                        fill = min(pos.sl, bid_open) - cm.slippage
                        close_position(pos, bar_close_time, fill, "sl")
                    elif bid_high >= pos.tp:
                        fill = max(pos.tp, bid_open)  # limit fills at limit or better
                        close_position(pos, bar_close_time, fill, "tp")
                    else:
                        still_open.append(pos)
                else:
                    # Short exits on the ask.
                    ask_open, ask_low, ask_high = cm.ask(row.open), cm.ask(row.low), cm.ask(row.high)
                    if ask_high >= pos.sl:
                        fill = max(pos.sl, ask_open) + cm.slippage
                        close_position(pos, bar_close_time, fill, "sl")
                    elif ask_low <= pos.tp:
                        fill = min(pos.tp, ask_open)
                        close_position(pos, bar_close_time, fill, "tp")
                    else:
                        still_open.append(pos)
            positions = still_open

            # 3. Signals off the bar closes, to be filled at the next bar's open.
            if session_label(bar_close_time, cfg.sessions) is not None:
                for row in group:
                    sig = self.strategy.signal_for_bar(row.instrument, row, bar_time)
                    if sig is not None:
                        pending[row.instrument] = sig

            # Mark to market on mid closes.
            for row in group:
                last_close[row.instrument] = row.close
            unrealized = sum(
                (last_close[p.instrument] - p.entry_price) * p.side * p.units
                for p in positions
            )
            eq_times.append(bar_time)
            eq_mtm.append(equity + unrealized)
            eq_realized.append(equity)

        # Force-close whatever is still open at the end of the data.
        for pos in list(positions):
            cm = cost_models[pos.instrument]
            fill = cm.market_exit_fill(pos.side, last_close[pos.instrument])
            close_position(pos, eq_times[-1] + step, fill, "end_of_data")
        if positions and eq_times:
            eq_mtm[-1] = equity
            eq_realized[-1] = equity
        positions = []

        equity_df = pd.DataFrame(
            {"equity": eq_mtm, "realized": eq_realized},
            index=pd.DatetimeIndex(eq_times, name="time"),
        )
        # Multiple instruments share timestamps; keep the last (fully updated) mark.
        equity_df = equity_df[~equity_df.index.duplicated(keep="last")]

        trades_df = pd.DataFrame([t.__dict__ for t in trades])
        return BacktestResult(
            trades=trades_df,
            equity=equity_df,
            initial_equity=cfg.risk.initial_equity,
            config=cfg,
        )
