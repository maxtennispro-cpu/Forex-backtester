"""Live trade signals for the dashboard.

Fetches the most recent M5 candles (OANDA when ``OANDA_API_KEY`` is set,
synthetic demo data otherwise), runs the same BollingerFade logic the
backtest uses over the last day of closed bars, and reports the signals it
finds — the most recent bar's signal, if any, is flagged as *current*.

Results are cached for a short TTL so page loads don't hammer the data
source; the cache is per-process, matching the single-worker deploy.
"""
from __future__ import annotations

import logging
import os
import threading
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from forex_backtester.config import BacktestConfig
from forex_backtester.oanda_client import OandaClient
from forex_backtester.sessions import session_label
from forex_backtester.strategy.mean_reversion import BollingerFade
from forex_backtester.synthetic import generate_candles

log = logging.getLogger(__name__)

INSTRUMENTS = ["EUR_USD", "GBP_USD"]
GRANULARITY = "M5"
GRANULARITY_MINUTES = 5
SCAN_HOURS = 24            # how far back the "recent signals" list looks
CACHE_TTL_SECONDS = 60


@dataclass(frozen=True)
class LiveSignal:
    instrument: str
    time: datetime          # open time of the bar whose close fired the signal
    side: str               # "long" / "short"
    ref_price: float        # that bar's close (entry would be ~next bar's open)
    target_pips: float
    stop_pips: float
    reason: str
    session: str | None     # session the entry would fall into (None = closed)
    is_current: bool        # fired on the most recent closed bar


@dataclass(frozen=True)
class InstrumentState:
    instrument: str
    last_bar_time: datetime
    last_close: float
    current: LiveSignal | None
    recent: list[LiveSignal] = field(default_factory=list)   # newest first


@dataclass(frozen=True)
class SignalsData:
    demo: bool              # True = synthetic data (no OANDA key / fetch failed)
    error: str | None
    as_of: datetime
    states: list[InstrumentState] = field(default_factory=list)

    @property
    def all_recent(self) -> list[LiveSignal]:
        merged = [s for st in self.states for s in st.recent]
        return sorted(merged, key=lambda s: s.time, reverse=True)


_cache: tuple[float, SignalsData] | None = None
_lock = threading.Lock()


def get_signals() -> SignalsData:
    global _cache
    now = _time.monotonic()
    if _cache is not None and now - _cache[0] < CACHE_TTL_SECONDS:
        return _cache[1]
    with _lock:
        if _cache is None or _time.monotonic() - _cache[0] >= CACHE_TTL_SECONDS:
            _cache = (_time.monotonic(), _compute())
    return _cache[1]


def _fetch_candles(demo: bool, start: datetime, end: datetime) -> dict:
    if demo:
        # Seed by day so the demo feed shows fresh (but stable) signals daily.
        day = int(end.strftime("%Y%m%d"))
        return {
            inst: generate_candles(inst, start, end, GRANULARITY_MINUTES,
                                   seed=(day + i * 101) % (2**32))
            for i, inst in enumerate(INSTRUMENTS)
        }
    client = OandaClient(os.environ["OANDA_API_KEY"],
                         os.environ.get("OANDA_ENVIRONMENT", "practice"))
    return {
        inst: client.fetch_candles(inst, GRANULARITY, start, end)
        for inst in INSTRUMENTS
    }


def _compute() -> SignalsData:
    cfg = BacktestConfig()
    strategy = BollingerFade(cfg.strategy)
    end = datetime.now(timezone.utc)
    # Enough history for the indicator warmup plus the scan window, padded
    # for weekends/market closures when no candles print.
    start = end - timedelta(hours=SCAN_HOURS + 4) - timedelta(days=2)

    demo = not os.environ.get("OANDA_API_KEY")
    error = None
    try:
        data = _fetch_candles(demo, start, end)
    except Exception as exc:  # network/auth failures degrade to demo data
        log.warning("live candle fetch failed, falling back to demo: %s", exc)
        demo, error = True, str(exc)
        data = _fetch_candles(True, start, end)

    scan_cutoff = end - timedelta(hours=SCAN_HOURS)
    step = timedelta(minutes=GRANULARITY_MINUTES)
    states = []
    for inst in INSTRUMENTS:
        df = data[inst]
        enriched = strategy.compute_indicators(df)
        signals: list[LiveSignal] = []
        last_time = enriched.index[-1].to_pydatetime()
        for row in enriched.tail(int(SCAN_HOURS * 60 / GRANULARITY_MINUTES)).itertuples():
            bar_time = row.Index.to_pydatetime()
            if bar_time < scan_cutoff:
                continue
            sig = strategy.signal_for_bar(inst, row, bar_time)
            if sig is None:
                continue
            signals.append(LiveSignal(
                instrument=inst,
                time=bar_time,
                side="long" if sig.side > 0 else "short",
                ref_price=float(row.close),
                target_pips=sig.target_pips,
                stop_pips=sig.stop_pips,
                reason=sig.reason,
                session=session_label(bar_time + step, cfg.sessions),
                is_current=bar_time == last_time,
            ))
        signals.reverse()
        states.append(InstrumentState(
            instrument=inst,
            last_bar_time=last_time,
            last_close=float(enriched["close"].iloc[-1]),
            current=next((s for s in signals if s.is_current), None),
            recent=signals,
        ))
    return SignalsData(demo=demo, error=error, as_of=end, states=states)
