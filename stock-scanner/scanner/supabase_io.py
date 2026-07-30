"""Thin Supabase (PostgREST) client.

Talks straight to the REST endpoint with the service-role key — no SDK
dependency, and trivially mockable in tests. All functions raise on
non-2xx responses so the nightly job fails loudly rather than silently
dropping rows.
"""
from __future__ import annotations

import os

import requests


def _base() -> tuple[str, dict]:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_KEY"]
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    return f"{url}/rest/v1", headers


def get_watchlist() -> list[str]:
    base, headers = _base()
    r = requests.get(f"{base}/watchlist?select=ticker", headers=headers, timeout=30)
    r.raise_for_status()
    return [row["ticker"] for row in r.json()]


def upsert_setups(rows: list[dict]) -> None:
    """Insert flagged setups; re-running the same day updates in place."""
    if not rows:
        return
    base, headers = _base()
    r = requests.post(
        f"{base}/setups?on_conflict=scan_date,ticker,setup_type",
        headers={**headers, "Prefer": "resolution=merge-duplicates"},
        json=rows,
        timeout=60,
    )
    r.raise_for_status()


def get_setups(filters: str) -> list[dict]:
    """GET /setups with a raw PostgREST filter string, e.g. 'scan_date=eq.2026-07-30'."""
    base, headers = _base()
    r = requests.get(f"{base}/setups?{filters}", headers=headers, timeout=60)
    r.raise_for_status()
    return r.json()


def update_setup(setup_id: int, patch: dict) -> None:
    base, headers = _base()
    r = requests.patch(
        f"{base}/setups?id=eq.{setup_id}", headers=headers, json=patch, timeout=30
    )
    r.raise_for_status()
