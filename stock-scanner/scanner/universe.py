"""Scan universe: S&P 500 + Nasdaq 100 (from Wikipedia) + Supabase watchlist.

Index constituents are scraped at run time so the list stays current; if a
fetch fails the scan degrades gracefully to whatever else resolved instead
of aborting the night's run.
"""
from __future__ import annotations

import logging

import pandas as pd
import requests

from supabase_io import get_watchlist

log = logging.getLogger(__name__)

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ100_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"
_UA = {"User-Agent": "Mozilla/5.0 (stock-scanner; personal research tool)"}


def _tables(url: str) -> list[pd.DataFrame]:
    resp = requests.get(url, headers=_UA, timeout=30)
    resp.raise_for_status()
    return pd.read_html(resp.text)


def _normalize(symbol: str) -> str:
    """Wikipedia uses BRK.B / BF.B; yfinance wants BRK-B / BF-B."""
    return symbol.strip().upper().replace(".", "-")


def sp500_tickers() -> list[str]:
    for table in _tables(SP500_URL):
        if "Symbol" in table.columns:
            return [_normalize(s) for s in table["Symbol"].astype(str)]
    raise ValueError("no Symbol column found on S&P 500 page")


def nasdaq100_tickers() -> list[str]:
    for table in _tables(NASDAQ100_URL):
        for col in ("Ticker", "Symbol"):
            if col in table.columns and len(table) > 80:
                return [_normalize(s) for s in table[col].astype(str)]
    raise ValueError("no ticker table found on Nasdaq-100 page")


def build_universe() -> list[str]:
    tickers: set[str] = set()
    for name, fetch in (("S&P 500", sp500_tickers), ("Nasdaq 100", nasdaq100_tickers)):
        try:
            batch = fetch()
            tickers.update(batch)
            log.info("%s: %d tickers", name, len(batch))
        except Exception as exc:
            log.warning("failed to fetch %s constituents, skipping: %s", name, exc)
    try:
        wl = get_watchlist()
        tickers.update(_normalize(t) for t in wl)
        log.info("watchlist: %d tickers", len(wl))
    except Exception as exc:
        log.warning("failed to fetch watchlist, skipping: %s", exc)
    if not tickers:
        raise RuntimeError("universe is empty — all sources failed")
    return sorted(tickers)
