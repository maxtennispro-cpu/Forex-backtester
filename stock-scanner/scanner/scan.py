#!/usr/bin/env python3
"""Nightly scan entry point.

    python scan.py                 # full run: scan -> store -> AI score -> backfill
    python scan.py --dry-run       # scan and print, write nothing
    python scan.py --no-ai         # store setups but skip the scoring pass
    python scan.py --tickers AAPL MSFT   # scan a specific list instead of the universe

Environment: SUPABASE_URL, SUPABASE_KEY, ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from ai_score import score_setups
from indicators import compute_all
from outcomes import backfill_outcomes
from prices import download_history
from setups import detect_setups
from supabase_io import get_setups, update_setup, upsert_setups
from universe import build_universe

log = logging.getLogger("scan")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="print results, write nothing")
    p.add_argument("--no-ai", action="store_true", help="skip the AI scoring pass")
    p.add_argument("--no-backfill", action="store_true", help="skip outcome backfill")
    p.add_argument("--tickers", nargs="+", help="scan these tickers instead of the universe")
    p.add_argument("--period", default="2y", help="history window to download (default 2y)")
    return p.parse_args()


def run_scan(tickers: list[str], period: str) -> list[dict]:
    frames = download_history(tickers, period=period)
    flagged: list[dict] = []
    for ticker, df in frames.items():
        try:
            flagged.extend(detect_setups(ticker, compute_all(df)))
        except Exception as exc:  # one bad ticker shouldn't kill the run
            log.warning("%s: setup detection failed: %s", ticker, exc)
    return flagged


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    tickers = args.tickers or build_universe()
    log.info("scanning %d tickers", len(tickers))
    flagged = run_scan(tickers, args.period)
    log.info("flagged %d setups", len(flagged))

    if args.dry_run:
        for row in sorted(flagged, key=lambda r: (r["setup_type"], r["ticker"])):
            ind = row["indicators"]
            print(f"{row['ticker']:<6} {row['setup_type']:<16} "
                  f"close={row['close']:<10.2f} rsi={ind['rsi'] or 0:.1f} "
                  f"relvol={ind['rel_volume'] or 0:.2f}")
        return 0

    if flagged:
        upsert_setups(flagged)
        log.info("wrote %d setups to Supabase", len(flagged))

    if not args.no_ai and flagged:
        today = date.today().isoformat()
        stored = get_setups(
            f"select=id,ticker,setup_type,close,indicators"
            f"&scan_date=eq.{today}&ai_score=is.null&limit=1000"
        )
        log.info("scoring %d unscored setups", len(stored))
        for setup_id, patch in score_setups(stored).items():
            update_setup(setup_id, patch)

    if not args.no_backfill:
        backfill_outcomes()

    return 0


if __name__ == "__main__":
    sys.exit(main())
