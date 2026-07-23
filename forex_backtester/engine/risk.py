"""Risk rules: fixed-fractional sizing, position cap, daily loss cutoff.

Sizing assumes USD-quoted instruments (EUR_USD, GBP_USD) and a USD account:
one pip on one unit is worth ``pip_size`` USD, so risking ``risk_per_trade``
of equity over ``stop_pips`` gives

    units = equity * risk_per_trade / (stop_pips * pip_size)

capped by ``max_leverage`` on notional. The daily loss cutoff halts *new*
entries for the remainder of the UTC day once realized losses reach
``daily_loss_limit`` of the day's starting equity; open positions keep their
stops and targets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from ..config import RiskConfig


@dataclass
class DailyState:
    day: date | None = None
    start_equity: float = 0.0
    realized_pnl: float = 0.0
    halted: bool = False


class RiskManager:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg
        self.daily = DailyState()

    # -- daily loss cutoff ---------------------------------------------------

    def roll_day(self, now: datetime, equity: float) -> None:
        """Reset daily counters on the first event of each UTC day."""
        d = now.date()
        if self.daily.day != d:
            self.daily = DailyState(day=d, start_equity=equity)

    def record_realized(self, pnl: float) -> None:
        self.daily.realized_pnl += pnl
        limit = self.cfg.daily_loss_limit * self.daily.start_equity
        if self.daily.realized_pnl <= -limit:
            self.daily.halted = True

    # -- entry gating --------------------------------------------------------

    def can_open(self, open_positions: int) -> bool:
        return not self.daily.halted and open_positions < self.cfg.max_open_positions

    def units_for_trade(
        self, equity: float, stop_pips: float, pip_size: float, price: float
    ) -> int:
        if equity <= 0 or stop_pips <= 0:
            return 0
        risk_amount = equity * self.cfg.risk_per_trade
        units = risk_amount / (stop_pips * pip_size)
        notional_cap = equity * self.cfg.max_leverage / price
        return int(min(units, notional_cap))
