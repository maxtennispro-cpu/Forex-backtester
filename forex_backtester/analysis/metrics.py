"""Performance metrics: headline stats plus per-session / per-instrument cuts.

All headline numbers are computed on the mark-to-market equity curve (so
drawdown includes open-trade excursion) and on the closed-trade list.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _trade_stats(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {
            "trades": 0, "wins": 0, "losses": 0, "win_rate": np.nan,
            "profit_factor": np.nan, "net_pnl": 0.0, "avg_win": np.nan,
            "avg_loss": np.nan, "avg_pips": np.nan, "expectancy": np.nan,
        }
    wins = trades[trades["pnl"] > 0]
    losses = trades[trades["pnl"] <= 0]
    gross_win = wins["pnl"].sum()
    gross_loss = -losses["pnl"].sum()
    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(trades),
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else np.inf,
        "net_pnl": trades["pnl"].sum(),
        "avg_win": wins["pnl"].mean() if len(wins) else np.nan,
        "avg_loss": losses["pnl"].mean() if len(losses) else np.nan,
        "avg_pips": trades["pips"].mean(),
        "expectancy": trades["pnl"].mean(),
    }


def max_drawdown(equity: pd.Series) -> tuple[float, float]:
    """Return (max drawdown fraction, max drawdown in currency)."""
    peak = equity.cummax()
    dd = equity - peak
    dd_frac = dd / peak
    return float(-dd_frac.min()), float(-dd.min())


def compute_metrics(trades: pd.DataFrame, equity: pd.DataFrame,
                    initial_equity: float) -> dict:
    stats = _trade_stats(trades)
    eq = equity["equity"]
    final = float(eq.iloc[-1]) if len(eq) else initial_equity
    dd_frac, dd_abs = max_drawdown(eq) if len(eq) else (np.nan, np.nan)

    daily = eq.resample("1D").last().dropna()
    daily_ret = daily.pct_change().dropna()
    sharpe = (
        float(np.sqrt(252) * daily_ret.mean() / daily_ret.std())
        if len(daily_ret) > 1 and daily_ret.std() > 0 else np.nan
    )

    stats.update({
        "initial_equity": initial_equity,
        "final_equity": final,
        "total_return": final / initial_equity - 1,
        "max_drawdown_pct": dd_frac,
        "max_drawdown_abs": dd_abs,
        "sharpe_daily": sharpe,
    })
    if not trades.empty:
        span_days = max(
            (trades["exit_time"].max() - trades["entry_time"].min()).days, 1
        )
        stats["trades_per_week"] = len(trades) / (span_days / 7)
    return stats


def session_breakdown(trades: pd.DataFrame) -> pd.DataFrame:
    """Stats grouped by the session regime at entry (london/overlap/newyork)."""
    if trades.empty:
        return pd.DataFrame()
    rows = {
        label: _trade_stats(group)
        for label, group in trades.groupby("session")
    }
    order = [s for s in ("london", "overlap", "newyork") if s in rows]
    return pd.DataFrame.from_dict(rows, orient="index").loc[order]


def instrument_breakdown(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    rows = {
        inst: _trade_stats(group)
        for inst, group in trades.groupby("instrument")
    }
    return pd.DataFrame.from_dict(rows, orient="index")


def _fmt_breakdown(df: pd.DataFrame) -> str:
    if df.empty:
        return "  (no trades)"
    view = pd.DataFrame({
        "trades": df["trades"],
        "win rate": (df["win_rate"] * 100).map("{:.1f}%".format),
        "profit factor": df["profit_factor"].map("{:.2f}".format),
        "net P&L": df["net_pnl"].map("{:+,.0f}".format),
        "avg pips": df["avg_pips"].map("{:+.2f}".format),
    })
    return view.to_string()


def format_report(metrics: dict, sessions: pd.DataFrame,
                  instruments: pd.DataFrame) -> str:
    m = metrics
    lines = [
        "=" * 62,
        "BACKTEST RESULTS",
        "=" * 62,
        f"Initial equity      : {m['initial_equity']:>14,.2f}",
        f"Final equity        : {m['final_equity']:>14,.2f}",
        f"Total return        : {m['total_return']:>13.2%}",
        f"Max drawdown        : {m['max_drawdown_pct']:>13.2%}  ({m['max_drawdown_abs']:,.0f})",
        f"Sharpe (daily ann.) : {m['sharpe_daily']:>14.2f}",
        "-" * 62,
        f"Trades              : {m['trades']:>10}   ({m.get('trades_per_week', float('nan')):.1f}/week)",
        f"Win rate            : {m['win_rate']:>13.2%}   ({m['wins']}W / {m['losses']}L)",
        f"Profit factor       : {m['profit_factor']:>14.2f}",
        f"Avg win / avg loss  : {m['avg_win']:>+10,.2f} / {m['avg_loss']:+,.2f}",
        f"Expectancy per trade: {m['expectancy']:>+14,.2f}",
        f"Avg pips per trade  : {m['avg_pips']:>+14.2f}",
        "-" * 62,
        "PER-SESSION BREAKDOWN (session at entry)",
        _fmt_breakdown(sessions),
        "-" * 62,
        "PER-INSTRUMENT BREAKDOWN",
        _fmt_breakdown(instruments),
        "=" * 62,
    ]
    return "\n".join(lines)
