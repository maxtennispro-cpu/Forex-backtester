# MindScan — personal AI stock scanner

An end-of-day scanner that flags technical setups across the S&P 500, Nasdaq
100, and your own watchlist, scores each one with Claude, and shows them on a
phone-friendly dashboard — alongside the historical hit rate of every setup
type, so you can see which ones have actually worked.

**These are setups to review, not recommendations.** Nothing in this project is
investment advice, the AI scores are opinions about chart structure rather than
forecasts, and the hit-rate stats are deliberately shown up front so the
numbers can't hide behind the presentation.

```
GitHub Actions (nightly, after US close)
  └─ scanner/scan.py
       ├─ yfinance EOD OHLCV  ──▶ indicators ──▶ setup detection
       ├─ Supabase  (setups + raw indicator values)
       ├─ Anthropic API       ──▶ score 1-100, 2-sentence rationale, invalidation level
       └─ outcome backfill    ──▶ what price did 5 / 10 / 20 days later

Vercel
  └─ web/  Next.js dashboard (password-gated, reads Supabase server-side)
```

## What it looks for

| Setup | Condition |
|---|---|
| **Breakout** | Close above a 20-day tight range (≤8% wide) on 2x+ average volume |
| **Volume spike** | 3x+ relative volume with a positive close |
| **Momentum** | RSI crossing up through 50 with a MACD bullish cross within 3 days |
| **Oversold bounce** | RSI under 30 with a reversal candle (green, closing in the upper half of the day's range) |

Every flagged setup stores its raw indicators: RSI(14), MACD (line/signal/
histogram plus days since the bullish cross), 20/50/200 SMA position, Bollinger
%B, 30-day relative volume, ATR(14), distance from the 52-week high, and the
detected consolidation range.

## Setup

### 1. Supabase

Create a project at [supabase.com](https://supabase.com), then open **SQL
Editor → New query**, paste [`schema.sql`](schema.sql), and run it. Grab
**Project Settings → API → Project URL** and the **`service_role`** key.

The service-role key bypasses row-level security, which is why it lives only in
GitHub Actions secrets and Vercel server-side env vars — never in the browser.
RLS is enabled with no public policies, so the anon key can't read anything.

### 2. The scanner

```bash
cd stock-scanner/scanner
pip install -r requirements.txt

export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_KEY=your-service-role-key
export ANTHROPIC_API_KEY=sk-ant-...

python scan.py --dry-run --tickers AAPL MSFT NVDA   # print, write nothing
python scan.py                                      # full nightly run
```

Flags: `--dry-run`, `--no-ai` (store setups without scoring), `--no-backfill`,
`--tickers ...`, `--period 2y`.

```bash
python -m pytest tests/ -q    # 30 tests, no network or credentials needed
```

### 3. Nightly cron

[`.github/workflows/nightly-scan.yml`](../.github/workflows/nightly-scan.yml)
runs at 22:00 UTC on weekdays (6pm ET during EDT, 5pm ET during EST). Add three
repository secrets under **Settings → Secrets and variables → Actions**:

- `SUPABASE_URL`
- `SUPABASE_KEY`
- `ANTHROPIC_API_KEY`

You can also trigger it by hand from the **Actions** tab, optionally scanning
just a few tickers or skipping the AI pass.

### 4. The dashboard on Vercel

```bash
cd stock-scanner/web
npm install
cp .env.example .env.local     # fill in the three values
npm run dev                    # http://localhost:3000
```

To deploy: import the repo at [vercel.com](https://vercel.com), set **Root
Directory** to `stock-scanner/web`, and add the same three environment
variables (`SUPABASE_URL`, `SUPABASE_KEY`, `APP_PASSWORD`). None of them are
`NEXT_PUBLIC_*`, so they stay server-side.

Access is a single password. `proxy.ts` gates every route and API handler; the
cookie stores a SHA-256 digest rather than the password, and if `APP_PASSWORD`
isn't set the app fails closed instead of serving data openly.

## The dashboard

- **Today** — the latest scan's setups ranked by AI score, each card showing
  the setup type, score, two-sentence rationale, invalidation level, key stats,
  and a 60-day mini chart. Filter by setup type and score threshold.
- **History** — hit rate and average/median return at 5, 10, and 20 days,
  broken out **by setup type** and **by AI score band**. The score-band table is
  the useful one: if the bands don't separate, the AI score isn't adding
  information, and the page says so.
- **Watchlist** — add or remove tickers; they feed straight into the nightly
  scan alongside the index constituents.

## Cost

The AI pass batches 8 setups per request behind a cached system prompt, so a
typical night (10–40 setups) is a handful of requests — cents per run at
`claude-sonnet-4-6` rates. Override the model with `ANTHROPIC_MODEL` if you
want to trade cost for depth.

## Honest limitations

- **A "hit" is just a higher close N trading days later.** No targets, no
  stops, no position sizing, no slippage or commission — so the hit rate
  measures whether setups pointed the right way, not what a strategy would have
  returned.
- **Outcomes are survivorship-prone.** The universe is scraped from today's
  index membership, so names that were dropped are missing from history.
- **No look-ahead in detection**, but the indicator thresholds were chosen by
  hand rather than fit to data — treat the setup definitions as a starting point
  and let the history view tell you which ones deserve attention.
- **The AI score is a judgment about chart structure**, produced from the same
  indicator values you can see on the card. It has no information about
  fundamentals, news, or earnings dates.
