from __future__ import annotations

from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "monthly_smallcap_momentum.ipynb"


def markdown(text: str):
    return nbf.v4.new_markdown_cell(text.strip())


def code(text: str):
    return nbf.v4.new_code_cell(text.strip())


def build() -> None:
    notebook = nbf.v4.new_notebook()
    notebook["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3"},
    }
    notebook["cells"] = [
        markdown(
            """
# Momentum accademico sulle small-cap contro XSMO

## tl;dr

XSMO è il benchmark più diretto, ma segue l'attuale indice small-cap momentum
solo dal 21 giugno 2019. Da luglio 2019 a maggio 2026 il portafoglio accademico
small/high-momentum rende il **16,92% annuo lordo contro il 14,10% di XSMO**, con
Sharpe 0,674 contro 0,594. Il vantaggio non è però producibile con evidenza:
il drawdown è peggiore (-29,72% contro -25,54%) e il bootstrap include zero.
Con un proxy di turnover annuo del 305%, il costo all-in deve restare sotto
40,4 bps per lato. In uno scenario retail ottimistico da 25 bps più i minimi
IBKR, 50.000 dollari non bastano e 100.000 dollari battono XSMO di appena 0,49
punti prima delle tasse.
"""
        ),
        markdown(
            """
## Context & Methods

Il test usa i portafogli mensili ufficiali Kenneth French/CRSP formati su size e
prior return. Per ogni mese il segnale è il rendimento cumulato da t−12 a t−2:
il mese più recente viene escluso. Il portafoglio principale è l'intersezione
fra azioni sotto la mediana di market cap e il tercile con momentum più alto,
pesata per capitalizzazione.

### Key Assumptions

- Finestra fattore: maggio 2013–maggio 2026, 157 mesi.
- Confronto diretto XSMO: luglio 2019–maggio 2026, 83 mesi. Prima del 21 giugno
  2019 il ticker seguiva altri indici e non è comparabile con il mandato attuale.
- Benchmark secondari: MTUM e IWM, total return da adjusted close.
- I rendimenti accademici sono lordi e non rappresentano un prodotto
  direttamente investibile; vengono stressati di 25, 50 e 100 bps al mese.
- Il turnover effettivo non è disponibile nei portafogli aggregati French. Il
  305% annuo è una proxy pubblicata per il momentum mensile 12–2; XSMO ha
  riportato turnover del 115% nell'ultimo esercizio.
- Il portafoglio French “small” non coincide esattamente con l'S&P SmallCap 600.
- Sharpe calcolato sui rendimenti mensili in eccesso rispetto al T-bill French.

Fonti costi: prospetto XSMO 2025, commissioni ufficiali IBKR e Novy-Marx &
Velikov, *A Taxonomy of Anomalies and their Trading Costs*.
"""
        ),
        code(
            """
from pathlib import Path
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from IPython.display import display

ROOT = Path.cwd()
OUTPUT = ROOT / "outputs" / "monthly_momentum"
plt.style.use("seaborn-v0_8-whitegrid")
COLORS = {"ink": "#243247", "blue": "#3266a8", "gold": "#c4932f", "orange": "#d97832", "open": "#b8c7d9"}
"""
        ),
        markdown("## Data\n\n### 1. Load and validate the common monthly panel"),
        code(
            """
source = pd.read_csv(OUTPUT / "source_returns.csv", parse_dates=["Date"]).set_index("Date")
metrics = pd.read_csv(OUTPUT / "metrics.csv").set_index("series")
equity = pd.read_csv(OUTPUT / "equity.csv", parse_dates=["Date"]).set_index("Date")
annual = pd.read_csv(OUTPUT / "annual_returns.csv").set_index("Year")
direct_metrics = pd.read_csv(OUTPUT / "direct_metrics.csv").set_index("series")
direct_equity = pd.read_csv(OUTPUT / "direct_equity.csv", parse_dates=["Date"]).set_index("Date")
direct_annual = pd.read_csv(OUTPUT / "direct_annual_returns.csv").set_index("Year")
buckets = pd.read_csv(OUTPUT / "bucket_metrics.csv")
gates = pd.read_csv(OUTPUT / "direct_gates.csv")
bootstrap = pd.read_csv(OUTPUT / "bootstrap_vs_xsmo.csv").iloc[0]
break_even = pd.read_csv(OUTPUT / "cost_break_even.csv")
cost_grid = pd.read_csv(OUTPUT / "turnover_cost_grid.csv")
capital_costs = pd.read_csv(OUTPUT / "capital_cost_scenarios.csv")
implementation = json.loads((OUTPUT / "implementation_cost_verdict.json").read_text(encoding="utf-8"))
quality = json.loads((OUTPUT / "validation_summary.json").read_text(encoding="utf-8"))

assert quality["status"] == "PASS"
assert len(source) == 157
assert source.isna().sum().sum() == 0
assert source.index.min() == pd.Timestamp("2013-05-31")
assert source.index.max() == pd.Timestamp("2026-05-31")
assert len(direct_equity) == 83
assert direct_equity.index.min() == pd.Timestamp("2019-07-31")
quality
"""
        ),
        markdown(
            """
## Results

### Il segnale momentum è presente nelle small-cap

All'interno dello stesso universo accademico, CAGR e Sharpe crescono passando
dal tercile loser al neutral e al winner. Quindi il test non rifiuta il fattore
momentum. Il confronto con XSMO serve invece a capire se costruire in proprio
aggiunge valore rispetto a un ETF già investibile.
"""
        ),
        code(
            """
display(buckets[["bucket", "cagr", "annualized_volatility", "sharpe", "max_drawdown"]])
fig, ax = plt.subplots(figsize=(8.5, 4.5))
values = 100 * buckets.cagr
x = np.arange(len(buckets))
bars = ax.bar(x, values, color=[COLORS["open"], COLORS["gold"], COLORS["blue"]], edgecolor=COLORS["ink"])
ax.set(title="CAGR dei portafogli small-cap per bucket momentum", ylabel="CAGR (%)", xlabel="")
ax.set_xticks(x, ["Low", "Neutral", "High"])
for bar, value in zip(bars, values):
    ax.text(bar.get_x()+bar.get_width()/2, value+0.25, f"{value:.2f}%", ha="center")
plt.tight_layout(); plt.show()
"""
        ),
        markdown(
            """
### Il portafoglio lordo supera XSMO, ma con più rischio

Nel periodo coerente con il mandato attuale di XSMO, un dollaro cresce a 2,95
nel portafoglio accademico lordo contro 2,49 in XSMO. Il CAGR è superiore di
2,82 punti e lo Sharpe di 0,080, ma il drawdown è peggiore di 4,18 punti.
"""
        ),
        code(
            """
comparison_names = ["Small momentum gross", "XSMO", "MTUM", "IWM", "Smallest-quintile momentum gross"]
display(direct_metrics.loc[comparison_names, ["months", "total_return", "cagr", "annualized_volatility", "sharpe", "max_drawdown", "worst_month"]])

fig, ax = plt.subplots(figsize=(9, 5))
for name, color, style in [
    ("Small momentum gross", COLORS["blue"], "-"),
    ("XSMO", COLORS["gold"], "-"),
    ("MTUM", COLORS["orange"], "--"),
    ("IWM", COLORS["ink"], "--"),
]:
    ax.plot(direct_equity.index, direct_equity[name], label=name, color=color, linestyle=style, linewidth=2)
ax.set(title="Crescita di 1 dollaro", ylabel="Valore cumulato", xlabel="")
ax.legend(frameon=False)
plt.tight_layout(); plt.show()
"""
        ),
        markdown(
            """
### Batte XSMO in cinque anni su sei, ma l'incertezza è ampia

Tra i sei anni completi 2020–2025, il portafoglio small-cap batte XSMO in cinque.
La differenza media annualizzata è +2,85 punti, ma il bootstrap circolare a
blocchi di 12 mesi va da -3,32 a +10,23 punti e include zero.
"""
        ),
        code(
            """
full_years = direct_annual.loc[2020:2025].copy()
full_years["excess_vs_xsmo"] = full_years["Small momentum gross"] - full_years["XSMO"]
display(full_years[["Small momentum gross", "XSMO", "MTUM", "IWM", "excess_vs_xsmo"]])
display(bootstrap.to_frame("value"))

fig, ax = plt.subplots(figsize=(9, 4.5))
values = 100 * full_years.excess_vs_xsmo
ax.bar(full_years.index.astype(str), values, color=COLORS["blue"], edgecolor=COLORS["ink"])
ax.axhline(0, color=COLORS["ink"], linewidth=1)
ax.set(title="Excess return annuale small momentum contro XSMO", ylabel="Differenza (punti %)", xlabel="Anno")
plt.xticks(rotation=45)
plt.tight_layout(); plt.show()
"""
        ),
        markdown(
            """
### Il break-even è circa 40 bps per lato

La proxy accademica per il momentum mensile è turnover one-way del 305% annuo.
Con questo ritmo il portafoglio batte XSMO soltanto se commissioni, spread,
slippage e impatto restano complessivamente sotto 40,4 bps per lato, prima
della fiscalità. La letteratura sul fattore UMD stima costi storici medi di
48,39 bps al mese: non è una stima corrente del nostro long-only, ma è un
segnale contrario forte.
"""
        ),
        code(
            """
display(break_even)
academic_grid = cost_grid[cost_grid.turnover_scenario.eq("Academic monthly momentum proxy")]
display(academic_grid[["all_in_cost_bps_per_side", "annual_trading_drag", "net_cagr", "cagr_gap_vs_xsmo", "beats_xsmo"]])

fig, ax = plt.subplots(figsize=(8.5, 4.5))
for label, group in cost_grid.groupby("turnover_scenario"):
    ax.plot(group.all_in_cost_bps_per_side, 100*group.net_cagr, marker="o", label=label)
ax.axhline(100*direct_metrics.loc["XSMO", "cagr"], color=COLORS["ink"], linestyle="--", label="XSMO")
ax.set(title="CAGR netto per turnover e costo di esecuzione", ylabel="CAGR (%)", xlabel="Costo all-in per lato (bps)")
ax.legend(frameon=False)
plt.tight_layout(); plt.show()
"""
        ),
        markdown(
            """
### I minimi IBKR rendono decisiva la dimensione del capitale

IBKR Pro Tiered pubblica 0,0035 dollari per azione con minimo 0,35 dollari per
ordine; Fixed ha minimo 1 dollaro. Con 120 ordini al mese, turnover 305% e 25
bps per lato esclusi i ticket, il minimo Tiered vale 5,04% annuo su 10.000
dollari, 2,02% su 25.000, 1,01% su 50.000 e 0,50% su 100.000. Lo scenario da
100.000 dollari conserva soltanto 0,49 punti di CAGR su XSMO prima di tasse,
venue fees e possibili costi superiori.
"""
        ),
        code(
            """
tiered = capital_costs[
    capital_costs.pricing_plan.eq("IBKR Pro Tiered")
    & capital_costs.orders_per_month.eq(120)
].copy()
display(tiered[["capital_usd", "annual_minimum_commissions_usd", "annual_total_drag_before_tax", "net_cagr", "cagr_gap_vs_xsmo", "beats_xsmo"]])

fig, ax = plt.subplots(figsize=(8.5, 4.5))
ax.bar(tiered.capital_usd.astype(str), 100*tiered.cagr_gap_vs_xsmo, color=COLORS["blue"], edgecolor=COLORS["ink"])
ax.axhline(0, color=COLORS["ink"], linewidth=1)
ax.set(title="Gap di CAGR contro XSMO per capitale", ylabel="Differenza (punti %)", xlabel="Capitale (USD)")
plt.tight_layout(); plt.show()
"""
        ),
        markdown(
            """
## Takeaways

- **Il fattore esiste:** dentro le small-cap, i winner 12–2 superano neutral e loser.
- **Supera XSMO solo lordo:** +2,82 punti di CAGR e Sharpe più alto, ma drawdown
  peggiore e solo 40,4 bps/lato di budget a turnover 305%.
- **L'evidenza è promettente ma inconclusiva:** 5 anni su 6 migliori, però il
  bootstrap include differenze negative e il quintile più piccolo è debole.
- **Decisione:** preferire XSMO e non costruire il portafoglio live. Solo un
  ledger point-in-time con turnover reale e fill paper inferiori alla soglia di
  break-even potrebbe riaprire la decisione.
"""
        ),
    ]

    NOTEBOOK.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(notebook, NOTEBOOK)
    client = NotebookClient(
        notebook,
        timeout=600,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    )
    client.execute()
    nbf.write(notebook, NOTEBOOK)
    print(NOTEBOOK)


if __name__ == "__main__":
    build()
