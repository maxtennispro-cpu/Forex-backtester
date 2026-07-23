"""FastAPI application: marketing site, accounts, and the gated dashboard.

Run locally with:

    uvicorn webapp.main:app --reload

Payments are intentionally a placeholder: checkout collects no card data
and simply activates the chosen plan on the account. The POST handler in
``checkout_submit`` is the single point where a real Stripe (or other PSP)
integration slots in later.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import auth, backtest_service, db, signals_service
from .plans import PAID_PLANS, PLAN_ORDER, PLANS, get_plan

HERE = Path(__file__).resolve().parent

app = FastAPI(title="MindsFX")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("APP_SECRET_KEY") or secrets.token_hex(32),
)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

templates = Jinja2Templates(directory=HERE / "templates")


def render(request: Request, name: str, **context) -> Response:
    user = auth.current_user(request)
    context.update(
        request=request,
        user=user,
        user_plan=get_plan(user["plan"]) if user else None,
        plans=[PLANS[k] for k in PLAN_ORDER],
    )
    return templates.TemplateResponse(request, name, context)


# --------------------------------------------------------------------------
# Marketing pages
# --------------------------------------------------------------------------

@app.get("/")
def index(request: Request):
    return render(request, "index.html")


@app.get("/pricing")
def pricing(request: Request):
    return render(request, "pricing.html")


@app.get("/health")
def health():
    return {"status": "ok"}


# --------------------------------------------------------------------------
# Accounts
# --------------------------------------------------------------------------

@app.get("/register")
def register_form(request: Request):
    return render(request, "register.html", error=None)


@app.post("/register")
def register_submit(request: Request, email: str = Form(...),
                    password: str = Form(...)):
    email = email.strip().lower()
    if "@" not in email or len(password) < 8:
        return render(request, "register.html",
                      error="Enter a valid email and a password of 8+ characters.")
    user_id = db.create_user(email, auth.hash_password(password))
    if user_id is None:
        return render(request, "register.html",
                      error="An account with that email already exists.")
    request.session["user_id"] = user_id
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/login")
def login_form(request: Request):
    return render(request, "login.html", error=None)


@app.post("/login")
def login_submit(request: Request, email: str = Form(...),
                 password: str = Form(...)):
    user = db.get_user_by_email(email.strip().lower())
    if user is None or not auth.verify_password(password, user["password_hash"]):
        return render(request, "login.html", error="Invalid email or password.")
    request.session["user_id"] = user["id"]
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


# --------------------------------------------------------------------------
# Members' dashboard (plan-gated)
# --------------------------------------------------------------------------

@app.get("/dashboard")
def dashboard(request: Request):
    user = auth.current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    plan = get_plan(user["plan"])
    data = backtest_service.get_dashboard_data()

    recent_trades = None
    if plan.trade_log and len(data.trades):
        recent_trades = data.trades.sort_values("exit_time").tail(25)
        recent_trades = recent_trades.iloc[::-1].to_dict(orient="records")

    return render(
        request, "dashboard.html",
        plan=plan,
        signals=signals_service.get_signals() if plan.live_signals else None,
        metrics=data.metrics,
        sessions=data.sessions.reset_index().to_dict(orient="records")
                 if plan.full_metrics and len(data.sessions) else None,
        instruments=data.instruments.reset_index().to_dict(orient="records")
                    if plan.full_metrics and len(data.instruments) else None,
        recent_trades=recent_trades,
        as_of=data.as_of,
        window_days=data.window_days,
    )


@app.get("/dashboard/chart.png")
def dashboard_chart(request: Request):
    user = auth.current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not get_plan(user["plan"]).equity_chart:
        return RedirectResponse("/pricing", status_code=303)
    png = backtest_service.get_dashboard_data().chart_png()
    return Response(png, media_type="image/png")


@app.get("/dashboard/trades.csv")
def dashboard_trades_csv(request: Request):
    user = auth.current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not get_plan(user["plan"]).trade_log:
        return RedirectResponse("/pricing", status_code=303)
    csv = backtest_service.get_dashboard_data().trades_csv()
    return Response(csv, media_type="text/csv", headers={
        "Content-Disposition": "attachment; filename=trades.csv",
    })


@app.get("/api/signals")
def api_signals(request: Request):
    """JSON feed of current + recent signals (Premium)."""
    user = auth.current_user(request)
    if user is None:
        return Response('{"error": "authentication required"}', status_code=401,
                        media_type="application/json")
    if not get_plan(user["plan"]).trade_log:
        return Response('{"error": "premium plan required"}', status_code=403,
                        media_type="application/json")
    data = signals_service.get_signals()
    return {
        "demo_data": data.demo,
        "as_of": data.as_of.isoformat(),
        "instruments": [
            {
                "instrument": st.instrument,
                "last_bar_time": st.last_bar_time.isoformat(),
                "last_close": st.last_close,
                "current_signal": _signal_json(st.current),
                "recent_signals": [_signal_json(s) for s in st.recent],
            }
            for st in data.states
        ],
    }


def _signal_json(s) -> dict | None:
    if s is None:
        return None
    return {
        "time": s.time.isoformat(),
        "side": s.side,
        "ref_price": s.ref_price,
        "target_pips": round(s.target_pips, 1),
        "stop_pips": round(s.stop_pips, 1),
        "session": s.session,
        "reason": s.reason,
    }


# --------------------------------------------------------------------------
# Checkout (placeholder — no real payment is taken)
# --------------------------------------------------------------------------

@app.get("/checkout/{plan_key}")
def checkout_form(request: Request, plan_key: str):
    user = auth.current_user(request)
    if user is None:
        return RedirectResponse(f"/login?next=/checkout/{plan_key}", status_code=303)
    if plan_key not in PAID_PLANS:
        return RedirectResponse("/pricing", status_code=303)
    return render(request, "checkout.html", plan=PLANS[plan_key])


@app.post("/checkout/{plan_key}")
def checkout_submit(request: Request, plan_key: str):
    user = auth.current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if plan_key not in PAID_PLANS:
        return RedirectResponse("/pricing", status_code=303)
    # Real payments slot in here: create a Stripe Checkout Session for the
    # plan's price and set the plan in the webhook on payment success,
    # instead of activating it directly.
    db.set_plan(user["id"], plan_key)
    return RedirectResponse("/dashboard", status_code=303)
