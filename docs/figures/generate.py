"""Render archived aggregate research tables. No downloads or new backtest."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "images"
OUT.mkdir(exist_ok=True)
INK, MUTED, TEAL, ORANGE = "#172033", "#64748b", "#0f766e", "#c65a32"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                     "text.color": INK, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": INK})


def frame(title, subtitle):
    fig, ax = plt.subplots(figsize=(12, 6.6), facecolor="white")
    fig.subplots_adjust(left=0.23, right=0.93, top=0.74, bottom=0.22)
    fig.text(0.065, 0.93, "SMALL CAP MOMENTUM  /  ARCHIVED RESEARCH", color=TEAL,
             fontsize=10, weight="bold")
    fig.text(0.065, 0.85, title, fontsize=21, weight="bold")
    fig.text(0.065, 0.795, subtitle, fontsize=11, color=MUTED)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color("#cbd5e1")
    ax.tick_params(axis="both", length=0, pad=10)
    ax.set_axisbelow(True)
    return fig, ax


def comparison():
    data = pd.read_csv(ROOT / "data/historical-comparison.csv")
    fig, ax = frame("The revised setup did not hold up in 2026",
                    "Mean net return per trade · 100 bps round-trip costs · original study summaries")
    labels = [f"{row['case'].replace(' · ', '  /  ')}\nn = {int(row['trades'])} trades"
              for _, row in data.iterrows()]
    values = data["expectancy_pct"] * 100
    colors = [ORANGE, TEAL, ORANGE]
    ax.barh(range(len(data)), values, height=0.49, color=colors)
    ax.set_yticks(range(len(data)), labels)
    ax.invert_yaxis()
    ax.set_xlim(-2.3, 1.35)
    ax.axvline(0, color=INK, linewidth=1)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}%"))
    ax.grid(axis="x", color="#e2e8f0", linewidth=0.8)
    for y, value in enumerate(values):
        ax.text(value + (0.055 if value >= 0 else -0.055), y, f"{value:+.2f}%",
                va="center", ha="left" if value >= 0 else "right", weight="bold", fontsize=13)
    fig.text(0.065, 0.095, "Decision: NO-GO. V2 was selected after inspecting V1; these are not portfolio returns.", fontsize=10)
    fig.text(0.065, 0.055, "2026 YTD refers to the archived study window. Source: docs/figures/data/historical-comparison.csv", fontsize=9, color=MUTED)
    fig.savefig(OUT / "research-comparison.png", dpi=160)
    plt.close(fig)


def costs():
    data = pd.read_csv(ROOT / "data/historical-cost-sensitivity.csv")
    fig, ax = frame("Execution costs erode the apparent edge",
                    "V2 mean net return per filled trade · archived cost scenarios")
    fig.subplots_adjust(left=0.105, right=0.91, top=0.70, bottom=0.25)
    for period, label, color in [
        ("primary_2021_2025", "2021–2025 · 70 trades", TEAL),
        ("shadow_2026", "2026 YTD · 21 trades", ORANGE),
    ]:
        rows = data[data["period"] == period].sort_values("total_cost_bps")
        x, y = rows["total_cost_bps"], rows["expectancy_filled_pct"] * 100
        ax.plot(x, y, color=color, linewidth=2.6, marker="o", markersize=7, label=label)
        for cost, value in zip(x, y):
            ax.annotate(f"{value:+.2f}%", (cost, value), xytext=(0, 11 if value > 0 else -20),
                        textcoords="offset points", ha="center", fontsize=10, color=color)
    ax.set_xticks([24, 50, 100, 200])
    ax.set_xlim(12, 215)
    ax.set_ylim(-3.5, 2.3)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}%"))
    ax.set_xlabel("Total round-trip cost (basis points)", labelpad=13)
    ax.axhline(0, color=INK, linewidth=1)
    ax.grid(axis="y", color="#e2e8f0", linewidth=0.8)
    ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0, 1.02), ncol=2, borderaxespad=0)
    fig.text(0.065, 0.095, "The earlier sample turns negative at 200 bps. The archived 2026 sample is negative in every shown scenario.", fontsize=10)
    fig.text(0.065, 0.055, "Historical per-trade summaries; no new backtest or live fills. Source: docs/figures/data/historical-cost-sensitivity.csv", fontsize=9, color=MUTED)
    fig.savefig(OUT / "cost-sensitivity.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    comparison()
    costs()
    print("Rendered two figures from the bundled historical aggregate tables.")
