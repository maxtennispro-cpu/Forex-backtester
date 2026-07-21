"""Execution cost model.

OANDA candles are pulled as **mid** prices; this model reconstructs bid/ask
by shifting mid by half the spread, and charges slippage on market orders:

* Market entry:  fill = open ask + slippage (long) / open bid - slippage (short)
* Take-profit:   a limit order; triggers when the relevant side of the book
                 (bid for longs, ask for shorts) reaches the limit; fills at
                 the limit price, or better on a favourable gap.
* Hard stop:     a stop-market order; triggers off the same side of the book
                 and pays slippage. On an adverse gap (bar opens through the
                 stop) it fills at the gapped open, not the stop price.

Net effect per round trip: the full 1-pip spread plus 0.5 pips slippage on
entry, plus another 0.5 pips if the exit was a stop.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import CostConfig


@dataclass(frozen=True)
class CostModel:
    costs: CostConfig
    pip_size: float

    @property
    def half_spread(self) -> float:
        return self.costs.spread_pips * self.pip_size / 2

    @property
    def slippage(self) -> float:
        return self.costs.slippage_pips * self.pip_size

    def bid(self, mid: float) -> float:
        return mid - self.half_spread

    def ask(self, mid: float) -> float:
        return mid + self.half_spread

    def entry_fill(self, side: int, open_mid: float) -> float:
        """Market-order fill at the bar open, spread + slippage against us."""
        if side > 0:
            return self.ask(open_mid) + self.slippage
        return self.bid(open_mid) - self.slippage

    def market_exit_fill(self, side: int, mid: float) -> float:
        """Closing market order (end of data / forced flat)."""
        if side > 0:
            return self.bid(mid) - self.slippage   # sell to close a long
        return self.ask(mid) + self.slippage       # buy to close a short
