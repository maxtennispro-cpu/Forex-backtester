"""Forex backtesting toolkit for OANDA v20 mid-price candle data.

Layout:
    config          -- every tunable in one place (frozen dataclasses)
    oanda_client    -- OANDA v20 REST candle fetcher with local caching
    sessions        -- London / New York session filter
    strategy/       -- broker-agnostic signal generation (pluggable into a
                       live engine: it only ever sees completed bars)
    engine/         -- backtest event loop, execution cost model, risk rules
    analysis/       -- performance metrics and plots
    synthetic       -- synthetic candle generator for offline smoke tests
"""

__version__ = "0.1.0"
