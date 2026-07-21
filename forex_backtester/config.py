"""Central configuration.

Everything the strategy, risk manager, and cost model can be tuned with lives
here so that a future live-trading engine can construct the exact same objects
from the exact same values.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: Price value of one pip, per instrument. Both majors we trade are quoted in
#: USD with 4 decimal places (a pip is the 4th decimal). JPY crosses would be
#: 0.01 -- add them here if the universe grows.
PIP_SIZES: dict[str, float] = {
    "EUR_USD": 0.0001,
    "GBP_USD": 0.0001,
}

DEFAULT_PIP_SIZE = 0.0001


def pip_size(instrument: str) -> float:
    return PIP_SIZES.get(instrument, DEFAULT_PIP_SIZE)


@dataclass(frozen=True)
class StrategyConfig:
    """Bollinger-band mean-reversion (fade) parameters."""

    bb_period: int = 20            # lookback for the moving average / std dev
    bb_std: float = 2.0            # band width in standard deviations
    min_target_pips: float = 8.0   # skip the trade if the reversion on offer is smaller
    max_target_pips: float = 15.0  # cap the take-profit at this distance
    stop_multiple: float = 1.5     # hard stop distance = target * stop_multiple
    require_band_cross: bool = True  # only fire on the bar that first closes outside
                                     # the band (prevents re-entering every bar of a
                                     # sustained trend)


@dataclass(frozen=True)
class RiskConfig:
    initial_equity: float = 100_000.0
    risk_per_trade: float = 0.01      # fraction of equity risked between entry and stop
    max_open_positions: int = 3       # portfolio-wide, across all instruments
    daily_loss_limit: float = 0.03    # halt new entries for the rest of the UTC day
                                      # once realized losses reach this fraction of
                                      # the day's starting equity
    max_leverage: float = 20.0        # safety cap on notional per position


@dataclass(frozen=True)
class CostConfig:
    """Execution cost assumptions, applied to every fill in the backtest.

    Candles are mid prices; bid/ask are reconstructed as mid -/+ half the
    spread. Market orders (entries and stop-outs) additionally pay slippage
    against the trade. Take-profit limit orders fill at their limit price.
    """

    spread_pips: float = 1.0
    slippage_pips: float = 0.5


@dataclass(frozen=True)
class SessionConfig:
    """Session windows in UTC hours [open, close).

    These are fixed-UTC approximations of the London (08:00-16:30 local) and
    New York (08:00-17:00 ET) cash sessions; they drift by an hour around DST
    transitions, which is acceptable for a first-pass backtest.
    """

    london_open: int = 7
    london_close: int = 16
    newyork_open: int = 12
    newyork_close: int = 21


@dataclass(frozen=True)
class BacktestConfig:
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    costs: CostConfig = field(default_factory=CostConfig)
    sessions: SessionConfig = field(default_factory=SessionConfig)
