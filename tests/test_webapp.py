"""Web app tests: routing, auth flow, and plan gating.

The heavy dashboard backtest is replaced with a tiny stub so these stay
fast; the real backtest pipeline is covered by test_backtester.py.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from webapp import backtest_service, db, signals_service
from webapp.backtest_service import DashboardData
from webapp.main import app
from webapp.signals_service import InstrumentState, LiveSignal, SignalsData


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Fresh sqlite db per test and a canned dashboard payload."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "app.db")

    trades = pd.DataFrame([{
        "instrument": "EUR_USD", "side": "long", "units": 10_000,
        "signal_time": datetime(2026, 7, 1, 9, 0),
        "entry_time": datetime(2026, 7, 1, 9, 5),
        "exit_time": datetime(2026, 7, 1, 11, 0),
        "entry_price": 1.0800, "exit_price": 1.0810,
        "pnl": 100.0, "pips": 10.0, "target_pips": 10.0, "stop_pips": 15.0,
        "session": "london", "exit_reason": "tp", "equity_after": 100_100.0,
    }])
    equity = pd.DataFrame(
        {"equity": [100_000.0, 100_100.0], "realized": [100_000.0, 100_100.0]},
        index=pd.DatetimeIndex(
            [datetime(2026, 7, 1, 9, 0), datetime(2026, 7, 1, 11, 0)],
            name="time",
        ),
    )
    stub = DashboardData(
        metrics={
            "trades": 1, "wins": 1, "losses": 0, "win_rate": 1.0,
            "profit_factor": float("inf"), "net_pnl": 100.0,
            "avg_win": 100.0, "avg_loss": float("nan"), "avg_pips": 10.0,
            "expectancy": 100.0, "initial_equity": 100_000.0,
            "final_equity": 100_100.0, "total_return": 0.001,
            "max_drawdown_pct": 0.0, "max_drawdown_abs": 0.0,
            "sharpe_daily": 1.5, "trades_per_week": 7.0,
        },
        sessions=pd.DataFrame(
            {"trades": [1], "win_rate": [1.0], "profit_factor": [2.0],
             "net_pnl": [100.0], "avg_pips": [10.0]},
            index=pd.Index(["london"]),
        ),
        instruments=pd.DataFrame(
            {"trades": [1], "win_rate": [1.0], "profit_factor": [2.0],
             "net_pnl": [100.0], "avg_pips": [10.0]},
            index=pd.Index(["EUR_USD"]),
        ),
        trades=trades,
        equity=equity,
        initial_equity=100_000.0,
        as_of=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(backtest_service, "get_dashboard_data", lambda: stub)

    sig = LiveSignal(
        instrument="EUR_USD", time=datetime(2026, 7, 21, 9, 0),
        side="short", ref_price=1.0850, target_pips=12.0, stop_pips=18.0,
        reason="close above 2sd band, 12.0 pips from mean",
        session="london", is_current=True,
    )
    signals_stub = SignalsData(
        demo=True, error=None,
        as_of=datetime(2026, 7, 21, 9, 5, tzinfo=timezone.utc),
        states=[
            InstrumentState(
                instrument="EUR_USD",
                last_bar_time=datetime(2026, 7, 21, 9, 0),
                last_close=1.0850, current=sig, recent=[sig],
            ),
            InstrumentState(
                instrument="GBP_USD",
                last_bar_time=datetime(2026, 7, 21, 9, 0),
                last_close=1.2700, current=None, recent=[],
            ),
        ],
    )
    monkeypatch.setattr(signals_service, "get_signals", lambda: signals_stub)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def register(client, email="user@example.com", password="hunter2secret"):
    return client.post("/register", data={"email": email, "password": password},
                       follow_redirects=False)


# ---------------------------------------------------------------------------

def test_public_pages(client):
    for path in ("/", "/pricing", "/login", "/register"):
        r = client.get(path)
        assert r.status_code == 200, path
    assert client.get("/health").json() == {"status": "ok"}


def test_pricing_lists_all_plans(client):
    body = client.get("/pricing").text
    for name in ("Starter", "Pro", "Premium"):
        assert name in body
    assert "$29" in body and "$79" in body


def test_register_login_logout_flow(client):
    r = register(client)
    assert r.status_code == 303 and r.headers["location"] == "/dashboard"
    assert client.get("/dashboard").status_code == 200

    client.get("/logout")
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"

    r = client.post("/login",
                    data={"email": "user@example.com", "password": "hunter2secret"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/dashboard"


def test_register_rejects_duplicate_and_weak_password(client):
    register(client)
    r = register(client)  # same email again
    assert "already exists" in r.text
    r = register(client, email="other@example.com", password="short")
    assert "8+ characters" in r.text


def test_bad_login_rejected(client):
    register(client)
    r = client.post("/login",
                    data={"email": "user@example.com", "password": "wrongpass1"})
    assert "Invalid email or password" in r.text


def test_free_plan_is_gated(client):
    register(client)
    body = client.get("/dashboard").text
    assert "Win rate" in body                    # headline stats visible
    assert "Upgrade to Pro" in body              # chart/metrics locked
    assert "Sharpe (ann.)" not in body
    r = client.get("/dashboard/chart.png", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/pricing"
    r = client.get("/dashboard/trades.csv", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/pricing"


def test_pro_upgrade_unlocks_chart_not_trades(client):
    register(client)
    r = client.post("/checkout/pro", follow_redirects=False)
    assert r.status_code == 303
    body = client.get("/dashboard").text
    assert "Sharpe" in body and "Per-session performance" in body
    assert "Upgrade to Premium" in body          # trade log still locked
    assert client.get("/dashboard/chart.png").headers["content-type"] == "image/png"
    r = client.get("/dashboard/trades.csv", follow_redirects=False)
    assert r.status_code == 303


def test_premium_unlocks_trade_log_and_csv(client):
    register(client)
    client.post("/checkout/premium")
    body = client.get("/dashboard").text
    assert "Recent trades" in body and "Download full CSV" in body
    r = client.get("/dashboard/trades.csv")
    assert r.headers["content-type"].startswith("text/csv")
    assert "EUR_USD" in r.text


def test_signals_gated_by_plan(client):
    register(client)
    body = client.get("/dashboard").text
    assert "Live trade signals" in body and "available on <strong>Pro" in body
    assert "SHORT" not in body

    client.post("/checkout/pro")
    body = client.get("/dashboard").text
    assert "Live signals" in body
    assert "SHORT @ ~1.08500" in body
    assert "No active signal" in body            # GBP/USD has no setup


def test_signals_api_requires_premium(client):
    assert client.get("/api/signals").status_code == 401
    register(client)
    assert client.get("/api/signals").status_code == 403   # free
    client.post("/checkout/pro")
    assert client.get("/api/signals").status_code == 403   # pro
    client.post("/checkout/premium")
    r = client.get("/api/signals")
    assert r.status_code == 200
    payload = r.json()
    assert payload["demo_data"] is True
    eur = payload["instruments"][0]
    assert eur["current_signal"]["side"] == "short"
    assert eur["current_signal"]["target_pips"] == 12.0


def test_checkout_rejects_unknown_and_free_plans(client):
    register(client)
    for bad in ("free", "enterprise"):
        r = client.get(f"/checkout/{bad}", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/pricing"


def test_checkout_requires_login(client):
    r = client.get("/checkout/pro", follow_redirects=False)
    assert r.status_code == 303 and "/login" in r.headers["location"]
