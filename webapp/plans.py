"""Subscription plan definitions and feature gating.

The plan a user is on is stored on their account row; every gated route
checks capability flags here rather than comparing plan names inline, so
adding a tier (or moving a feature between tiers) is a one-file change.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Plan:
    key: str
    name: str
    price_monthly: float          # USD; 0 = free
    tagline: str
    features: list[str] = field(default_factory=list)
    # capability flags consumed by the routes
    full_metrics: bool = False    # drawdown/Sharpe/expectancy + breakdowns
    equity_chart: bool = False
    trade_log: bool = False       # recent trades table + CSV export
    live_signals: bool = False    # current + recent strategy signals
    highlighted: bool = False     # visual emphasis on the pricing page


PLANS: dict[str, Plan] = {
    "free": Plan(
        key="free",
        name="Starter",
        price_monthly=0.0,
        tagline="See the strategy in action",
        features=[
            "Live demo backtest (EUR/USD + GBP/USD)",
            "Headline stats: return, win rate, trade count",
            "Strategy methodology overview",
        ],
    ),
    "pro": Plan(
        key="pro",
        name="Pro",
        price_monthly=29.0,
        tagline="Full performance analytics",
        features=[
            "Everything in Starter",
            "Live trade signals (EUR/USD & GBP/USD)",
            "Full metrics: Sharpe, drawdown, profit factor, expectancy",
            "Equity curve & drawdown chart",
            "Per-session and per-instrument breakdowns",
        ],
        full_metrics=True,
        equity_chart=True,
        live_signals=True,
        highlighted=True,
    ),
    "premium": Plan(
        key="premium",
        name="Premium",
        price_monthly=79.0,
        tagline="Every trade, exportable",
        features=[
            "Everything in Pro",
            "Signals API (JSON) for automation",
            "Complete trade log with entry/exit detail",
            "CSV export of trades",
            "Priority support",
        ],
        full_metrics=True,
        equity_chart=True,
        trade_log=True,
        live_signals=True,
    ),
}

#: Display order on the pricing page.
PLAN_ORDER = ["free", "pro", "premium"]

#: Plans that can be purchased through checkout (everything but free).
PAID_PLANS = [k for k in PLAN_ORDER if PLANS[k].price_monthly > 0]


def get_plan(key: str | None) -> Plan:
    return PLANS.get(key or "free", PLANS["free"])
