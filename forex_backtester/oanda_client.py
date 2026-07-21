"""OANDA v20 REST candle fetcher.

Pulls mid-price candles from ``/v3/instruments/{instrument}/candles``,
paginating in blocks of 5000 (the API maximum) and retrying transient
failures with exponential backoff. Results are cached locally as csv.gz so a
3-year pull (~220k five-minute bars per pair) only hits the API once.

Credentials come from the environment:

    OANDA_API_KEY       -- required (a practice-account token)
    OANDA_ENVIRONMENT   -- "practice" (default) or "live"
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)

HOSTS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}

GRANULARITY_SECONDS = {
    "M1": 60, "M2": 120, "M4": 240, "M5": 300, "M10": 600, "M15": 900,
    "M30": 1800, "H1": 3600, "H2": 7200, "H4": 14400, "D": 86400,
}

MAX_CANDLES_PER_REQUEST = 5000
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class OandaError(RuntimeError):
    pass


class OandaClient:
    def __init__(self, api_key: str, environment: str = "practice", timeout: int = 30):
        if environment not in HOSTS:
            raise OandaError(f"unknown OANDA environment {environment!r}")
        self.base_url = HOSTS[environment]
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Accept-Datetime-Format": "RFC3339",
        })

    def _get(self, path: str, params: dict) -> dict:
        url = f"{self.base_url}{path}"
        for attempt in range(5):
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in RETRYABLE_STATUS:
                wait = 2 ** attempt
                log.warning("OANDA %s -> HTTP %s, retrying in %ss",
                            path, resp.status_code, wait)
                time.sleep(wait)
                continue
            raise OandaError(
                f"OANDA request failed: HTTP {resp.status_code} {resp.text[:300]}"
            )
        raise OandaError(f"OANDA request failed after retries: {url}")

    def fetch_candles(
        self,
        instrument: str,
        granularity: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Fetch complete mid-price candles for [start, end), UTC-indexed."""
        if granularity not in GRANULARITY_SECONDS:
            raise OandaError(f"unsupported granularity {granularity!r}")
        step = timedelta(seconds=GRANULARITY_SECONDS[granularity])
        start = start.astimezone(timezone.utc)
        end = end.astimezone(timezone.utc)

        rows: dict[pd.Timestamp, tuple] = {}
        cursor = start
        while cursor < end:
            payload = self._get(
                f"/v3/instruments/{instrument}/candles",
                {
                    "granularity": granularity,
                    "price": "M",
                    "from": cursor.isoformat().replace("+00:00", "Z"),
                    "count": MAX_CANDLES_PER_REQUEST,
                },
            )
            candles = payload.get("candles", [])
            new = 0
            last_time = cursor
            for c in candles:
                t = pd.Timestamp(c["time"]).tz_convert("UTC")
                last_time = t.to_pydatetime()
                if not c.get("complete", False) or t >= end:
                    continue
                if t not in rows:
                    new += 1
                mid = c["mid"]
                rows[t] = (
                    float(mid["o"]), float(mid["h"]), float(mid["l"]),
                    float(mid["c"]), int(c.get("volume", 0)),
                )
            log.info("%s %s: %d candles through %s (%d total)",
                     instrument, granularity, new, last_time, len(rows))
            if not candles or last_time <= cursor:
                break  # reached the present (or an empty stretch); no progress
            cursor = last_time + step
            time.sleep(0.1)  # be polite to the rate limiter

        if not rows:
            raise OandaError(
                f"no candles returned for {instrument} {granularity} "
                f"between {start} and {end}"
            )
        df = pd.DataFrame.from_dict(
            rows, orient="index",
            columns=["open", "high", "low", "close", "volume"],
        ).sort_index()
        df.index.name = "time"
        return df


def load_candles(
    client: OandaClient | None,
    instrument: str,
    granularity: str,
    start: datetime,
    end: datetime,
    cache_dir: Path,
    refresh: bool = False,
) -> pd.DataFrame:
    """Cached wrapper around :meth:`OandaClient.fetch_candles`."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / (
        f"{instrument}_{granularity}_{start:%Y%m%d}_{end:%Y%m%d}.csv.gz"
    )
    if cache_file.exists() and not refresh:
        log.info("loading %s from cache %s", instrument, cache_file.name)
        return pd.read_csv(cache_file, index_col="time", parse_dates=["time"])
    if client is None:
        raise OandaError(
            f"no cached data at {cache_file} and no OANDA client available "
            "(set OANDA_API_KEY in .env)"
        )
    df = client.fetch_candles(instrument, granularity, start, end)
    df.to_csv(cache_file)
    log.info("cached %d candles to %s", len(df), cache_file.name)
    return df
