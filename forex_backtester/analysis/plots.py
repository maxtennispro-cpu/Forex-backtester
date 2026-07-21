"""Equity-curve chart (PNG via matplotlib).

Two stacked panels sharing the time axis: mark-to-market equity on top,
drawdown below. One series per panel (titles carry identity, so no legend),
thin 2px-ish lines, recessive grid and axes, all text in ink tokens rather
than series colors.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Light-surface palette (categorical slot 1 for the equity line; the reserved
# "critical" status red for drawdown, which is a state, not a series).
SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
SERIES_BLUE = "#2a78d6"
DRAWDOWN_RED = "#d03b3b"


def plot_equity_curve(equity: pd.DataFrame, initial_equity: float,
                      out_path: Path, title: str = "Equity curve") -> Path:
    eq = equity["equity"]
    peak = eq.cummax()
    drawdown_pct = (eq - peak) / peak * 100

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(12, 7), sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08},
    )
    fig.patch.set_facecolor(SURFACE)

    for ax in (ax1, ax2):
        ax.set_facecolor(SURFACE)
        ax.grid(True, color=GRIDLINE, linewidth=0.8)
        ax.tick_params(colors=INK_MUTED, labelsize=9)
        for spine in ax.spines.values():
            spine.set_color(BASELINE)
        ax.spines[["top", "right"]].set_visible(False)

    ax1.plot(eq.index, eq.values, color=SERIES_BLUE, linewidth=1.6)
    ax1.axhline(initial_equity, color=BASELINE, linewidth=1, linestyle="--")
    ax1.set_title(title, color=INK_PRIMARY, fontsize=13, loc="left", pad=12)
    ax1.set_ylabel("Equity (account ccy)", color=INK_SECONDARY, fontsize=10)
    ax1.yaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}")
    )

    ax2.fill_between(drawdown_pct.index, drawdown_pct.values, 0,
                     color=DRAWDOWN_RED, alpha=0.35, linewidth=0)
    ax2.plot(drawdown_pct.index, drawdown_pct.values,
             color=DRAWDOWN_RED, linewidth=1.0)
    ax2.set_ylabel("Drawdown %", color=INK_SECONDARY, fontsize=10)
    ax2.set_ylim(top=0.5)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    return out_path
