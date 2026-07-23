# Forex Backtester — Bollinger-Fade Mean Reversion on OANDA

A Python backtesting system for OANDA v20 candle data. It pulls 3 years of
5-minute EUR/USD and GBP/USD mid-price candles from a practice account,
runs a Bollinger-band mean-reversion strategy during London/New York
sessions, and reports equity curve, win rate, profit factor, max drawdown,
and a per-session breakdown — with realistic spread and slippage baked into
every fill.

## Quick start

```bash
cd forex-backtester
pip install -r requirements.txt

cp .env.example .env          # then paste your OANDA practice API key
python run_backtest.py        # pulls & caches 3y of M5 candles, runs, reports
```

No API key handy? Validate the whole pipeline on synthetic data:

```bash
python run_backtest.py --synthetic
```

Useful flags: `--years 1`, `--instruments EUR_USD`, `--granularity M15`,
`--refresh` (ignore the candle cache), `--output-dir`.

Outputs land in `output/`: `report.txt` (also printed), `equity_curve.png`,
`trades.csv`, `equity_curve.csv`, `summary.json`. Candles cache to `data/`
as csv.gz, so the 3-year pull (~45 paginated requests per pair) happens once.

Run the tests:

```bash
python -m pytest tests/ -q
```

## Web app (subscription site)

`webapp/` wraps the backtester in a small subscription site — marketing
landing page, pricing page with Starter/Pro/Premium tiers, user accounts,
and a members' dashboard whose gated content is live backtester output
(run on synthetic candles, so no OANDA key is needed):

```bash
uvicorn webapp.main:app --reload    # then open http://127.0.0.1:8000
```

- **Starter (free)** — headline stats (return, win rate, trade count).
- **Pro** — live trade signals, full metrics (Sharpe, drawdown, profit
  factor, expectancy), equity/drawdown chart, per-session and
  per-instrument breakdowns.
- **Premium** — everything in Pro plus a JSON signals API (`/api/signals`),
  the complete trade log, and CSV export.

### Live signals

The dashboard's **Live signals** panel runs the BollingerFade strategy on
the most recent M5 candles and shows the current setup (side, reference
price, target/stop in pips, session) plus every signal from the last 24
hours. Without credentials it runs on a demo data feed and says so; to use
real market prices, set `OANDA_API_KEY` (a free practice-account token
from oanda.com — Manage API Access) in `.env` locally, or add it as an
environment variable on your Render service (Environment tab) and
redeploy. Signals are research output from an unproven strategy — trade
them at your own risk.

Checkout is a placeholder (no payment is collected; confirming activates
the plan). A real Stripe integration slots into `checkout_submit` in
`webapp/main.py`. Users live in SQLite under `webapp/data/` (gitignored);
set `APP_SECRET_KEY` in `.env` to keep sessions across restarts.

### Deploying it

The repo ships with a `render.yaml` blueprint: on [render.com](https://render.com),
choose **New + → Blueprint**, connect this repository, and it deploys the
site to a public URL on the free plan (a random `APP_SECRET_KEY` is
generated for you). Any Docker host works too:

```bash
docker build -t mindsfx .
docker run -p 8000:8000 mindsfx
```

Note the SQLite user database is on local disk — on free hosts with
ephemeral storage, accounts reset on redeploy. Fine for a demo; attach a
persistent disk or move to a hosted database before real users.

## The strategy

`forex_backtester/strategy/mean_reversion.py` — **BollingerFade**:

- 20-period SMA with 2-standard-deviation bands on M5 closes.
- When a bar **closes beyond a band** (the move has extended 2+σ from the
  mean), fade it: short above the upper band, long below the lower band.
  Only the *first* close outside the band fires (`require_band_cross`), so a
  trend riding the band produces one fade, not one per bar.
- **Take-profit**: the reversion back to the middle band, clamped to
  **8–15 pips**. If the mean is closer than 8 pips, the edge can't clear
  costs and the setup is skipped.
- **Hard stop**: 1.5× the target distance (configurable), attached at entry.
- Signals are generated — and entries filled — only during London/NY hours.

All knobs live in `forex_backtester/config.py` (`StrategyConfig`,
`RiskConfig`, `CostConfig`, `SessionConfig`).

## Execution & cost model

Candles are mid prices; bid/ask are reconstructed as mid ∓/± half the
**1-pip spread**:

| Order | Trigger | Fill |
|---|---|---|
| Entry (market, next bar open) | — | open ± (half-spread + **0.5 pip slippage**) against the trade |
| Take-profit (limit) | bid (longs) / ask (shorts) touches the limit | limit price, or better on a favourable gap |
| Stop (stop-market) | same side of book crosses the stop | stop ± slippage; an **adverse gap fills at the gapped open**, not the stop |

If a bar's range contains both the stop and the target, the **stop is
assumed to fill first** (worst case). Signals fill at the *next* bar's open —
no same-bar-close fills, no lookahead.

## Risk rules

- **1% of equity risked per trade**: units = equity × 1% ÷ (stop distance),
  capped at 20× leverage on notional.
- **Max 3 open positions** portfolio-wide across both pairs.
- **Daily loss cutoff**: once realized losses reach 3% of the UTC day's
  starting equity, no new entries until the next day (open positions keep
  their stops/targets).
- End of data force-closes remaining positions at market with full costs.

## Sessions

Fixed-UTC approximations (they drift an hour around DST): London 07:00–16:00,
New York 12:00–21:00. Trades are tagged at entry as `london`, `overlap`
(12:00–16:00, both open), or `newyork` for the per-session breakdown.

## Layout — designed for a live engine later

```
forex_backtester/
├── config.py              # every tunable, shared by backtest & future live engine
├── oanda_client.py        # v20 REST fetcher (pagination, retries, local cache)
├── sessions.py            # London/NY windows + labels
├── synthetic.py           # offline smoke-test data
├── strategy/              # ← the pluggable part
│   ├── base.py            # Strategy interface + Signal dataclass
│   └── mean_reversion.py  # BollingerFade
├── engine/
│   ├── execution.py       # spread/slippage cost model
│   ├── risk.py            # sizing, position cap, daily cutoff
│   └── backtest.py        # merged-stream event loop over both instruments
└── analysis/
    ├── metrics.py         # win rate, PF, max DD, session/instrument cuts
    └── plots.py           # equity-curve + drawdown PNG
```

The strategy contract (`strategy/base.py`) is what makes it pluggable: a
strategy only ever sees **completed bars** and emits `Signal` intents in
pips — it never touches the account, broker, or clock. The backtester uses
the vectorized path (`compute_indicators` + `signal_for_bar`); a live engine
feeds a rolling window of closed candles to `Strategy.on_bar(instrument,
history)` and routes the returned `Signal` through its own execution — the
same `RiskManager` (sizing/cutoffs) and `CostModel` types are importable
as-is. Both paths run identical logic.

## Assumptions & caveats

- Mid-candle bid/ask reconstruction with a *fixed* 1-pip spread is
  conservative for EUR/USD in session (typically <1 pip on OANDA) and
  slightly optimistic around news spikes; slippage covers part of that.
- Intra-bar path is unknown: stop-before-target on ambiguous bars is the
  conservative resolution.
- Session windows are fixed UTC (no DST tracking); the daily loss cutoff
  keys on UTC days, not the NY-17:00 forex day roll.
- Sizing assumes a USD-denominated account trading USD-quoted pairs (pip
  value = pip size × units). Financing/swap costs are not modeled — targets
  are 8–15 pips and holds are typically well under a day.
