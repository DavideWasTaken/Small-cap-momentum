from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mplfinance as mpf
import numpy as np
import pandas as pd

from .backtest import Trade
from .config import BacktestConfig


COLORS = {
    "blue": "#2563EB",
    "orange": "#EA580C",
    "gold": "#CA8A04",
    "ink": "#172033",
    "muted": "#64748B",
    "grid": "#E2E8F0",
}


def plot_trade(trade: Trade, frame: pd.DataFrame, cfg: BacktestConfig, output: str | Path) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    entry_loc = frame.index.get_indexer([trade.entry_time], method="nearest")[0]
    exit_loc = frame.index.get_indexer([trade.exit_time], method="nearest")[0]
    start = max(0, entry_loc - cfg.output.chart_bars_before)
    end = min(len(frame), max(exit_loc + cfg.output.chart_bars_after + 1, entry_loc + 8))
    window = frame.iloc[start:end][["Open", "High", "Low", "Close", "Volume"]].copy()
    entry_marks = pd.Series(np.nan, index=window.index)
    exit_marks = pd.Series(np.nan, index=window.index)
    if trade.entry_time in entry_marks.index:
        entry_marks.loc[trade.entry_time] = trade.entry_price_raw
    if trade.exit_time in exit_marks.index:
        exit_marks.loc[trade.exit_time] = trade.exit_price_raw
    addplots = [
        mpf.make_addplot(entry_marks, type="scatter", marker="^", markersize=110, color=COLORS["blue"]),
        mpf.make_addplot(exit_marks, type="scatter", marker="v", markersize=110, color=COLORS["orange"]),
    ]
    market = mpf.make_marketcolors(
        up="#2563EB", down="#EA580C", edge="inherit", wick="inherit", volume="inherit"
    )
    style = mpf.make_mpf_style(
        marketcolors=market,
        facecolor="white",
        figcolor="white",
        gridcolor=COLORS["grid"],
        gridstyle="--",
        rc={"font.size": 9, "axes.labelcolor": COLORS["ink"], "text.color": COLORS["ink"]},
    )
    fig, axes = mpf.plot(
        window,
        type="candle",
        volume=True,
        addplot=addplots,
        hlines={
            "hlines": [trade.resistance_level, trade.stop_price],
            "colors": [COLORS["gold"], COLORS["orange"]],
            "linestyle": ["--", ":"],
            "linewidths": [1.4, 1.1],
        },
        style=style,
        returnfig=True,
        figsize=(13, 7),
        tight_layout=True,
        datetime_format="%m-%d %H:%M",
        xrotation=20,
        warn_too_much_data=2000,
    )
    axes[0].set_title(
        f"{trade.ticker} | {trade.variant} | entry {trade.entry_price_raw:.3f} | "
        f"exit {trade.exit_price_raw:.3f} ({trade.return_pct:+.1%})",
        loc="left",
        fontsize=13,
        fontweight="bold",
    )
    axes[0].text(
        0.01,
        0.98,
        f"resistenza {trade.resistance_level:.3f} ({trade.resistance_source}, {trade.resistance_tests} test)\n"
        f"stop {trade.stop_price:.3f} | uscita {trade.exit_reason}",
        transform=axes[0].transAxes,
        va="top",
        ha="left",
        bbox={"facecolor": "white", "edgecolor": COLORS["grid"], "alpha": 0.9},
    )
    fig.savefig(output, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return output


def plot_equity_curve(equity: pd.DataFrame, output: str | Path) -> Path | None:
    if equity.empty:
        return None
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 6), facecolor="white")
    palette = [COLORS["blue"], COLORS["orange"], COLORS["gold"], COLORS["muted"]]
    for color, (variant, group) in zip(palette, equity.groupby("variant", sort=True)):
        ax.plot(group["trade"], group["equity"], marker="o", linewidth=2, label=variant, color=color)
    ax.set_title("Equity curve a trade chiuso", loc="left", fontsize=14, fontweight="bold")
    ax.set_xlabel("Numero progressivo di trade")
    ax.set_ylabel("Equity ($)")
    ax.grid(axis="y", color=COLORS["grid"], linestyle="--")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, ncol=2)
    fig.tight_layout()
    fig.savefig(output, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return output


def plot_variant_returns(metrics: pd.DataFrame, output: str | Path) -> Path | None:
    if metrics.empty:
        return None
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    ordered = metrics.sort_values("expectancy_pct")
    fig, ax = plt.subplots(figsize=(9, 5), facecolor="white")
    ax.barh(ordered["variant"], ordered["expectancy_pct"] * 100, color=COLORS["blue"])
    ax.axvline(0, color=COLORS["ink"], linewidth=0.8)
    ax.set_title("Expectancy media per variante", loc="left", fontsize=14, fontweight="bold")
    ax.set_xlabel("Rendimento medio netto per trade (%)")
    ax.grid(axis="x", color=COLORS["grid"], linestyle="--")
    ax.spines[["top", "right", "left"]].set_visible(False)
    for idx, value in enumerate(ordered["expectancy_pct"] * 100):
        ax.text(value, idx, f" {value:+.2f}%", va="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(output, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return output
