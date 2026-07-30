"""Tests for the AI scoring layer and the outcome backfill.

The Anthropic client is mocked, so these run without credentials and
without spending tokens. What they pin down is the request/response
contract: a schema the API will accept, correct parsing, score clamping,
and graceful degradation when a chunk fails.
"""
from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import ai_score
import outcomes


# --------------------------------------------------------------------------
# AI scoring
# --------------------------------------------------------------------------

def make_setup(setup_id: int, ticker: str = "AAPL") -> dict:
    return {
        "id": setup_id,
        "ticker": ticker,
        "setup_type": "breakout",
        "close": 210.5,
        "indicators": {"rsi": 61.2, "rel_volume": 2.4, "above_sma200": True},
    }


class FakeMessages:
    """Records requests and replays canned responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps(result))],
            usage=SimpleNamespace(input_tokens=100, output_tokens=50,
                                 cache_read_input_tokens=0),
        )


@pytest.fixture
def fake_client(monkeypatch):
    holder = {}

    def install(responses):
        messages = FakeMessages(responses)
        monkeypatch.setattr(
            ai_score.anthropic, "Anthropic",
            lambda *a, **k: SimpleNamespace(messages=messages),
        )
        holder["messages"] = messages
        return messages

    holder["install"] = install
    return holder


def test_output_schema_satisfies_structured_output_rules():
    """Every object needs additionalProperties: false and a required list."""
    def check(node):
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False
            assert node.get("required"), node
            for child in node.get("properties", {}).values():
                check(child)
        elif node.get("type") == "array":
            check(node["items"])

    check(ai_score.OUTPUT_SCHEMA["schema"])
    assert ai_score.OUTPUT_SCHEMA["type"] == "json_schema"


def test_score_setups_parses_results(fake_client):
    fake_client["install"]([{"results": [
        {"id": 1, "score": 82, "rationale": "Clean break. Volume confirms.",
         "invalidation": "below 205.00, the range high"},
    ]}])
    scores = ai_score.score_setups([make_setup(1)])
    assert scores == {1: {
        "ai_score": 82,
        "ai_rationale": "Clean break. Volume confirms.",
        "ai_invalidation": "below 205.00, the range high",
    }}


def test_score_setups_sends_cached_system_prompt_and_schema(fake_client):
    messages = fake_client["install"]([{"results": [
        {"id": 1, "score": 50, "rationale": "x", "invalidation": "y"},
    ]}])
    ai_score.score_setups([make_setup(1)])
    req = messages.requests[0]
    assert req["model"] == ai_score.MODEL
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert req["output_config"]["format"] is ai_score.OUTPUT_SCHEMA
    # Only compact per-setup data rides in the user turn.
    sent = json.loads(req["messages"][0]["content"])
    assert sent == [{"id": 1, "ticker": "AAPL", "setup_type": "breakout",
                     "close": 210.5,
                     "indicators": {"rsi": 61.2, "rel_volume": 2.4,
                                    "above_sma200": True}}]


def test_score_setups_batches_by_chunk_size(fake_client):
    n = ai_score.CHUNK_SIZE * 2 + 1
    setups = [make_setup(i) for i in range(n)]
    responses = []
    for start in range(0, n, ai_score.CHUNK_SIZE):
        chunk = setups[start:start + ai_score.CHUNK_SIZE]
        responses.append({"results": [
            {"id": s["id"], "score": 55, "rationale": "r", "invalidation": "i"}
            for s in chunk
        ]})
    messages = fake_client["install"](responses)
    scores = ai_score.score_setups(setups)
    assert len(messages.requests) == 3      # 8 + 8 + 1
    assert len(scores) == n


def test_score_setups_clamps_out_of_range_scores(fake_client):
    fake_client["install"]([{"results": [
        {"id": 1, "score": 150, "rationale": "r", "invalidation": "i"},
        {"id": 2, "score": -5, "rationale": "r", "invalidation": "i"},
    ]}])
    scores = ai_score.score_setups([make_setup(1), make_setup(2, "MSFT")])
    assert scores[1]["ai_score"] == 100
    assert scores[2]["ai_score"] == 1


def test_score_setups_survives_failed_and_malformed_chunks(fake_client):
    good = {"results": [{"id": 9, "score": 70, "rationale": "r", "invalidation": "i"}]}
    fake_client["install"]([
        ai_score.anthropic.APIError("boom", request=None, body=None),  # chunk 1
        good,                                                          # chunk 2
    ])
    setups = [make_setup(i) for i in range(ai_score.CHUNK_SIZE + 1)]
    scores = ai_score.score_setups(setups)
    assert 9 in scores and len(scores) == 1      # first chunk dropped, run continues


def test_score_setups_no_input_makes_no_request(fake_client):
    messages = fake_client["install"]([])
    assert ai_score.score_setups([]) == {}
    assert messages.requests == []


# --------------------------------------------------------------------------
# Outcome backfill
# --------------------------------------------------------------------------

def closes_series(values, start="2026-06-01"):
    idx = pd.date_range(start, periods=len(values), freq="B")
    return pd.Series(np.asarray(values, float), index=idx)


def test_forward_return_computes_percent_change():
    closes = closes_series([100, 101, 102, 103, 104, 110])
    scan_day = closes.index[0].date()
    assert outcomes._forward_return(closes, scan_day, 5) == pytest.approx(10.0)
    assert outcomes._forward_return(closes, scan_day, 2) == pytest.approx(2.0)


def test_forward_return_none_when_horizon_not_elapsed():
    closes = closes_series([100, 101, 102])
    assert outcomes._forward_return(closes, closes.index[0].date(), 5) is None


def test_forward_return_none_when_scan_day_missing():
    closes = closes_series([100, 101, 102, 103, 104, 105])
    assert outcomes._forward_return(closes, date(2020, 1, 1), 5) is None


def test_backfill_updates_only_elapsed_horizons(monkeypatch):
    closes = closes_series([100] + [100] * 5 + [110] + [120] * 4)  # 11 bars
    scan_day = closes.index[0].date().isoformat()
    pending = [{"id": 7, "ticker": "AAPL", "scan_date": scan_day,
                "fwd_5d": None, "fwd_10d": None, "fwd_20d": None}]
    patches = {}

    monkeypatch.setattr(outcomes, "get_setups", lambda f: pending)
    monkeypatch.setattr(outcomes, "download_history",
                        lambda t, period="6mo": {"AAPL": pd.DataFrame({"close": closes})})
    monkeypatch.setattr(outcomes, "update_setup",
                        lambda i, p: patches.setdefault(i, {}).update(p))

    assert outcomes.backfill_outcomes() == 1
    assert set(patches[7]) == {"fwd_5d", "fwd_10d"}     # 20d hasn't elapsed
    assert patches[7]["fwd_5d"] == pytest.approx(0.0)
    assert patches[7]["fwd_10d"] == pytest.approx(20.0)


def test_backfill_skips_already_filled_fields(monkeypatch):
    closes = closes_series([100] * 6 + [105])
    scan_day = closes.index[0].date().isoformat()
    pending = [{"id": 3, "ticker": "MSFT", "scan_date": scan_day,
                "fwd_5d": 1.23, "fwd_10d": None, "fwd_20d": None}]
    patches = {}
    monkeypatch.setattr(outcomes, "get_setups", lambda f: pending)
    monkeypatch.setattr(outcomes, "download_history",
                        lambda t, period="6mo": {"MSFT": pd.DataFrame({"close": closes})})
    monkeypatch.setattr(outcomes, "update_setup",
                        lambda i, p: patches.setdefault(i, {}).update(p))

    outcomes.backfill_outcomes()
    assert "fwd_5d" not in patches.get(3, {})   # existing value left alone


def test_backfill_with_nothing_pending(monkeypatch):
    monkeypatch.setattr(outcomes, "get_setups", lambda f: [])
    assert outcomes.backfill_outcomes() == 0
