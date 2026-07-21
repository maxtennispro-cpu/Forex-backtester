#!/usr/bin/env python3
"""Run the Bollinger-fade mean-reversion backtest on OANDA candles.

Typical use (3 years of 5-minute EUR/USD + GBP/USD, practice account):

    python run_backtest.py

Requires OANDA_API_KEY in .env (or the
environment). Candles are cached under backtester/data/ after the first
pull. To validate the pipeline without credentials:

    python run_backtest.py --synthetic

Outputs (backtester/output/ by default): a printed report, equity_curve.png,
trades.csv, equity_curve.csv, and summary.json.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from forex_backtester.analysis.metrics import (
    compute_metrics, format_report, instrument_breakdown, session_breakdown,
)
from forex_backtester.analysis.plots import plot_equity_curve
from forex_backtester.config import BacktestConfig
from forex_backtester.engine.backtest import Backtester
from forex_backtester.oanda_client import OandaClient, load_candles
from forex_backtester.strategy.mean_reversion import BollingerFade
from forex_backtester.synthetic import generate_candles

GRANULARITY_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--instruments", nargs="+", default=["EUR_USD", "GBP_USD"])
    p.add_argument("--granularity", default="M5", choices=GRANULARITY_MINUTES)
    p.add_argument("--years", type=float, default=3.0,
                   help="lookback window ending today (default: 3)")
    p.add_argument("--synthetic", action="store_true",
                   help="use synthetic data instead of OANDA (no API key needed)")
    p.add_argument("--refresh", action="store_true",
                   help="ignore the local candle cache and re-fetch")
    p.add_argument("--output-dir", type=Path, default=HERE / "output")
    p.add_argument("--data-dir", type=Path, default=HERE / "data")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def build_client() -> OandaClient | None:
    load_dotenv(HERE / ".env")
    api_key = os.environ.get("OANDA_API_KEY")
    if not api_key:
        return None
    environment = os.environ.get("OANDA_ENVIRONMENT", "practice")
    return OandaClient(api_key, environment)


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("run_backtest")

    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=round(args.years * 365))

    data = {}
    if args.synthetic:
        log.info("generating synthetic candles (%s -> %s)", start.date(), end.date())
        for inst in args.instruments:
            data[inst] = generate_candles(inst, start, end,
                                          GRANULARITY_MINUTES[args.granularity])
    else:
        client = build_client()
        if client is None and args.refresh:
            log.error("OANDA_API_KEY not set -- create .env "
                      "(see .env.example) or run with --synthetic")
            return 1
        for inst in args.instruments:
            data[inst] = load_candles(client, inst, args.granularity, start, end,
                                      cache_dir=args.data_dir, refresh=args.refresh)

    for inst, df in data.items():
        log.info("%s: %d candles, %s -> %s", inst, len(df),
                 df.index[0], df.index[-1])

    config = BacktestConfig()
    strategy = BollingerFade(config.strategy)
    result = Backtester(strategy, config).run(
        data, granularity_minutes=GRANULARITY_MINUTES[args.granularity]
    )

    metrics = compute_metrics(result.trades, result.equity, result.initial_equity)
    sessions = session_breakdown(result.trades)
    instruments = instrument_breakdown(result.trades)
    report = format_report(metrics, sessions, instruments)
    print(report)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    result.trades.to_csv(out / "trades.csv", index=False)
    result.equity.to_csv(out / "equity_curve.csv")
    plot_equity_curve(
        result.equity, result.initial_equity, out / "equity_curve.png",
        title=f"Bollinger fade -- {', '.join(args.instruments)} "
              f"{args.granularity} ({'synthetic' if args.synthetic else 'OANDA'})",
    )
    serializable = {k: (None if isinstance(v, float) and v != v else v)
                    for k, v in metrics.items()}
    (out / "summary.json").write_text(json.dumps({
        "metrics": serializable,
        "sessions": json.loads(sessions.to_json(orient="index")) if len(sessions) else {},
        "instruments": json.loads(instruments.to_json(orient="index")) if len(instruments) else {},
    }, indent=2, default=str))
    (out / "report.txt").write_text(report)
    log.info("outputs written to %s", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
