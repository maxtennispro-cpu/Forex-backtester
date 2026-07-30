"""AI scoring of flagged setups via the Anthropic API.

Setups are scored in chunks (several per request) with a stable, cached
system prompt, so token cost stays low: the rubric is written once per
cache window and each request only pays for the compact indicator JSON.
Structured outputs (`output_config.format`) guarantee parseable JSON.

The scorer never sees or produces buy/sell advice — it grades setup
quality and risk/reward and proposes an invalidation level, framed as
research to review.
"""
from __future__ import annotations

import json
import logging
import os

import anthropic

log = logging.getLogger(__name__)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
CHUNK_SIZE = 8

SYSTEM_PROMPT = """\
You are a quantitative analyst grading technical stock setups for a personal
research dashboard. You are NOT giving investment advice and must never use
buy/sell/recommendation language — these are setups to review, nothing more.

For each setup you receive (ticker, setup type, and raw indicator values from
today's close), return:
- score: integer 1-100 for overall setup quality and risk/reward. Calibrate
  hard: 80+ means textbook-quality with clean structure and favorable
  risk/reward; 50 is mediocre; below 30 is a poor or contradictory setup.
  Consider: trend alignment (price vs 20/50/200 SMAs), volume confirmation
  (rel_volume), how extended price is (bb_percent_b, pct_from_52w_high),
  volatility context (atr relative to price), and internal consistency
  between the indicators and the claimed setup type.
- rationale: exactly 2 plain-English sentences explaining the score. Mention
  the strongest factor for and the biggest risk against the setup.
- invalidation: a concrete price level (a number) at which the setup thesis
  is invalidated, derived from the structure (e.g. below the breakout range
  high, below the reversal candle low, or ~1.5 ATR under the close), plus a
  short phrase saying what it is based on.

Setup type definitions:
- breakout: close above a multi-week tight range on 2x+ average volume
- volume_spike: 3x+ relative volume with a positive close
- momentum: RSI crossed up through 50 with a MACD bullish cross within 3 days
- oversold_bounce: RSI under 30 with a reversal candle

Score each setup independently. Return one result per input, same order."""

OUTPUT_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "score": {"type": "integer"},
                        "rationale": {"type": "string"},
                        "invalidation": {"type": "string"},
                    },
                    "required": ["id", "score", "rationale", "invalidation"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["results"],
        "additionalProperties": False,
    },
}


def _payload(setup: dict) -> dict:
    return {
        "id": setup["id"],
        "ticker": setup["ticker"],
        "setup_type": setup["setup_type"],
        "close": setup["close"],
        "indicators": setup["indicators"],
    }


def score_setups(setups: list[dict]) -> dict[int, dict]:
    """Score setups (each dict needs an ``id``); returns {id: patch}."""
    if not setups:
        return {}
    client = anthropic.Anthropic()
    scores: dict[int, dict] = {}
    for start in range(0, len(setups), CHUNK_SIZE):
        chunk = setups[start:start + CHUNK_SIZE]
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=[{
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }],
                output_config={"format": OUTPUT_SCHEMA},
                messages=[{
                    "role": "user",
                    "content": json.dumps([_payload(s) for s in chunk]),
                }],
            )
        except anthropic.APIError as exc:
            log.error("scoring request failed for chunk at %d: %s", start, exc)
            continue
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            results = json.loads(text)["results"]
        except (json.JSONDecodeError, KeyError) as exc:
            log.error("unparseable scoring response: %s", exc)
            continue
        for r in results:
            score = max(1, min(100, int(r["score"])))
            scores[int(r["id"])] = {
                "ai_score": score,
                "ai_rationale": str(r["rationale"]).strip(),
                "ai_invalidation": str(r["invalidation"]).strip(),
            }
        log.info("scored %d setups (tokens in=%d out=%d, cache_read=%d)",
                 len(results), response.usage.input_tokens,
                 response.usage.output_tokens,
                 getattr(response.usage, "cache_read_input_tokens", 0) or 0)
    return scores
