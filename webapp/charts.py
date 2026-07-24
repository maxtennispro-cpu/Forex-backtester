"""Dark-themed live price chart (PNG) for the dashboard.

Candlesticks of the most recent bars with the Bollinger bands the strategy
trades and a marker on every bar whose close fired a signal. Rendered from
the same cached candle feed the signals come from, styled to sit on the
site's dark panels.
"""
from __future__ import annotations

import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BG = "#161e2a"
INK = "#e8edf4"
INK_MUTED = "#6b7686"
GRID = "#24304055"
UP = "#23c186"
DOWN = "#e0564f"
BAND = "#5b8fd9"

CHART_BARS = 96          # 8 hours of M5


def render_live_chart(state, bars: int = CHART_BARS) -> bytes:
    """``state`` is a signals_service.InstrumentState with a candles frame."""
    df = state.candles.tail(bars)
    x = np.arange(len(df))
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))

    fig, ax = plt.subplots(figsize=(11, 4.0))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    for spine in ax.spines.values():
        spine.set_visible(False)

    # Bollinger bands behind the candles.
    if "bb_upper" in df:
        ax.fill_between(x, df["bb_lower"], df["bb_upper"],
                        color=BAND, alpha=0.08, linewidth=0)
        for col in ("bb_upper", "bb_lower"):
            ax.plot(x, df[col], color=BAND, linewidth=0.9, alpha=0.7)
        ax.plot(x, df["bb_mid"], color=BAND, linewidth=0.9, alpha=0.5,
                linestyle="--")

    # Candles: high-low wick plus open-close body.
    up = c >= o
    ax.vlines(x, l, h, color=np.where(up, UP, DOWN), linewidth=0.8, alpha=0.9)
    body = np.where(np.abs(c - o) > 0, c - o, (h - l) * 0.02)  # visible doji
    ax.bar(x[up], body[up], bottom=o[up], width=0.62, color=UP)
    ax.bar(x[~up], body[~up], bottom=o[~up], width=0.62, color=DOWN)

    # Signal markers on the bars that fired.
    pad = (h.max() - l.min()) * 0.04 or 0.0005
    for sig in state.recent:
        try:
            pos = df.index.get_loc(sig.time)
        except KeyError:
            continue
        if sig.side == "long":
            ax.scatter(pos, l[pos] - pad, marker="^", s=90, color=UP,
                       edgecolors=BG, linewidths=0.8, zorder=5)
        else:
            ax.scatter(pos, h[pos] + pad, marker="v", s=90, color=DOWN,
                       edgecolors=BG, linewidths=0.8, zorder=5)

    step = max(len(df) // 8, 1)
    ticks = x[::step]
    ax.set_xticks(ticks)
    ax.set_xticklabels([df.index[i].strftime("%H:%M") for i in ticks])
    ax.set_xlim(-1, len(df))
    ax.yaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.4f}"))
    ax.set_title(
        f"{state.instrument.replace('_', '/')}  ·  M5  ·  last {c[-1]:.5f}",
        color=INK, fontsize=12, loc="left", pad=10)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return buf.getvalue()
