from __future__ import annotations

from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "strategy_go_no_go.ipynb"


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
# Strategia small-cap momentum: decisione go/no-go

## tl;dr

**No-go: scartare la formalizzazione attuale e non collegarla a IBKR.** La v1 è
negativa su 83 trade 2021–2025 a 100 bps (PF 0,741; expectancy -0,782%). La v2
porta il PF a 1,395 e l'expectancy a +0,849% sullo stesso periodo, ma è stata
scelta dopo aver osservato i dati, il bootstrap include zero e il controllo 2026
crolla a PF 0,434 ed expectancy -1,764%. Fra 21 combinazioni testate, nessuna
supera tutti i gate sul solo development e nessuna resta positiva in tutte le
quattro finestre temporali.
"""
        ),
        markdown(
            """
## Context & Methods

Il notebook verifica la decisione di continuare, automatizzare o scartare la
strategia. Carica i ledger rigenerati da 301 finestre Alpaca SIP e gli audit
salvati; non chiama API e non legge credenziali.

### Key Assumptions

- Periodo v1 primario: 2021–2025; costo operativo principale: 100 bps round-trip.
- Ricerca v2: 7 varianti di setup × 3 varianti di rischio/uscita = 21 combinazioni.
- Gate diagnostico di selezione sul solo 2021–2023: almeno 25 trade, PF ≥ 1,30,
  expectancy > 0 e mediana > 0. Se nessuna passa, non viene selezionata una
  candidata “meno peggio”.
- 2024, 2025 e 2026 sono letti in sequenza; la v2 pubblicata non è un test
  veramente vergine perché è stata scelta dopo l'esplorazione del campione.
- Restano survivorship bias, assenza di delisted point-in-time, bid/ask, halt/LULD
  e portfolio engine con posizioni concorrenti.
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
DECISION = ROOT / "outputs" / "strategy_decision"
V1 = ROOT / "outputs" / "historical_alpaca"
V2 = ROOT / "outputs" / "v2_candidate"

plt.style.use("seaborn-v0_8-whitegrid")
COLORS = {"ink": "#243247", "blue": "#3266a8", "gold": "#c4932f", "open": "#b8c7d9"}
"""
        ),
        markdown("## Data\n\n### 1. Load and reconcile the decision artifacts"),
        code(
            """
summary = json.loads((DECISION / "decision_summary.json").read_text(encoding="utf-8"))
development = pd.read_csv(DECISION / "candidate_development_audit.csv")
stability = pd.read_csv(DECISION / "candidate_period_stability.csv")
annual = pd.read_csv(DECISION / "v2_annual_100bps.csv")
costs = pd.read_csv(DECISION / "v2_cost_sensitivity.csv")
v1_checks = pd.read_csv(V1 / "validation_checks.csv")
v2_gates = pd.read_csv(V2 / "gates.csv")

assert summary["candidate_combinations_tested"] == 21
assert summary["development_candidates_passing_all_gates"] == 0
assert summary["candidates_positive_in_all_four_periods"] == 0
assert (v1_checks.query("severity == 'decision'")["status"] == "FAIL").all()
assert int(v2_gates["pass"].sum()) == 2
summary
"""
        ),
        markdown(
            """
## Results

### La v1 è negativa; la v2 migliora il passato ma fallisce il controllo successivo

La v2 recupera il periodo 2021–2025, ma la stima non è confermata e cambia segno
nel 2026. Il passaggio da +0,849% a -1,764% per trade è troppo ampio per trattare
la candidata come un edge stabile.
"""
        ),
        code(
            """
comparison = pd.DataFrame([
    {"case": "v1 · 2021–2025", **summary["v1"]},
    {"case": "v2 · 2021–2025", **summary["v2_primary"]},
    {"case": "v2 · 2026 YTD", **summary["v2_shadow_2026"]},
])
display(comparison[["case", "trades", "win_rate", "profit_factor", "expectancy_pct", "median_return_pct"]])

fig, ax = plt.subplots(figsize=(8.5, 4.5))
values = 100 * comparison["expectancy_pct"]
bars = ax.bar(comparison["case"], values, color=[COLORS["open"], COLORS["blue"], COLORS["gold"]], edgecolor=COLORS["ink"])
ax.axhline(0, color=COLORS["ink"], linewidth=1)
ax.set(title="Expectancy netta nei tre casi decisionali", ylabel="Expectancy per trade (%)", xlabel="")
for bar, value in zip(bars, values):
    ax.text(bar.get_x() + bar.get_width()/2, value + (0.06 if value >= 0 else -0.06), f"{value:.2f}%", ha="center", va="bottom" if value >= 0 else "top")
plt.tight_layout()
plt.show()
"""
        ),
        markdown(
            """
### La selezione anti-overfitting non promuove alcuna combinazione

Nessuna delle 21 combinazioni supera congiuntamente i gate nel solo 2021–2023.
La regola corretta è fermarsi, non scegliere retroattivamente la combinazione che
appare migliore dopo avere incluso 2024 e 2025.
"""
        ),
        code(
            """
display(development[[
    "setup", "risk", "trades", "profit_factor", "expectancy_pct",
    "median_return_pct", "development_gate_pass"
]].head(10))
display(pd.DataFrame({
    "combinazioni_testate": [len(development)],
    "pass development": [int(development.development_gate_pass.sum())],
    "positive in tutte le finestre": [int(stability.all_periods_positive.sum())],
}))
"""
        ),
        markdown(
            """
### La v2 dipende dal regime 2023–2025

La candidata stretta è negativa nel 2021, 2022 e 2026; è positiva solo nel
triennio 2023–2025. Il risultato aggregato nasconde quindi una forte instabilità
temporale.
"""
        ),
        code(
            """
annual_plot = annual.sort_values("year").copy()
annual_plot["expectancy_display"] = 100 * annual_plot["expectancy_filled_pct"]
display(annual_plot[["year", "filled_trades", "win_rate", "profit_factor", "expectancy_display", "median_return_pct"]])

fig, ax = plt.subplots(figsize=(8.5, 4.5))
bars = ax.bar(annual_plot.year.astype(str), annual_plot.expectancy_display, color=COLORS["blue"], edgecolor=COLORS["ink"])
ax.axhline(0, color=COLORS["ink"], linewidth=1)
ax.set(title="Expectancy annuale della candidata v2", xlabel="Anno", ylabel="Expectancy per trade (%)")
for bar, value in zip(bars, annual_plot.expectancy_display):
    ax.text(bar.get_x()+bar.get_width()/2, value + (0.05 if value >= 0 else -0.05), f"{value:.2f}%", ha="center", va="bottom" if value >= 0 else "top")
plt.tight_layout()
plt.show()
"""
        ),
        markdown(
            """
### Il margine economico non è sufficiente per small-cap live

Nel 2021–2025 la v2 è positiva a 100 bps ma torna negativa a 200 bps. Nel 2026
è negativa a tutti i costi testati. Poiché il modello non osserva spread,
partial fill, halt, LULD e impatto, il risultato non offre un margine prudente
per un'esecuzione automatica reale.
"""
        ),
        code(
            """
cost_plot = costs.copy()
cost_plot["period_label"] = cost_plot.period.map({"primary_2021_2025": "2021–2025", "shadow_2026": "2026 YTD"})
cost_plot["expectancy_display"] = 100 * cost_plot.expectancy_filled_pct
pivot = cost_plot.pivot(index="total_cost_bps", columns="period_label", values="expectancy_display")
display(cost_plot[["period_label", "total_cost_bps", "filled_trades", "profit_factor", "expectancy_display", "median_return_pct"]])

fig, ax = plt.subplots(figsize=(8.5, 4.5))
x = np.arange(len(pivot.index)); width = 0.36
ax.bar(x-width/2, pivot["2021–2025"], width, label="2021–2025", color=COLORS["blue"], edgecolor=COLORS["ink"])
ax.bar(x+width/2, pivot["2026 YTD"], width, label="2026 YTD", color=COLORS["gold"], edgecolor=COLORS["ink"])
ax.axhline(0, color=COLORS["ink"], linewidth=1)
ax.set(title="Expectancy v2 per scenario di costo", xlabel="Costo round-trip (bps)", ylabel="Expectancy per trade (%)", xticks=x, xticklabels=pivot.index.astype(int))
ax.legend(frameon=False)
plt.tight_layout()
plt.show()
"""
        ),
        markdown(
            """
## Takeaways

- **Decisione:** scartare v1 e v2 come candidate per produzione; non costruire
  ora l'adapter ordini IBKR.
- Continuare a ritoccare soglie sullo stesso storico aumenterebbe il
  data-snooping. Un eventuale nuovo tentativo deve essere una strategia v3 con
  ipotesi diversa, regole congelate e universo point-in-time.
- Prima del paper trading servono almeno 100 trade realmente out-of-sample, PF
  ≥ 1,30 dopo 100 bps, mediana positiva, limite inferiore dell'intervallo sopra
  zero e stabilità in almeno quattro anni su cinque.
- Solo dopo questi gate avrebbe senso raccogliere almeno 50 shadow/paper fill su
  IBKR per misurare spread e slippage reale; il paper trading non serve a
  dimostrare un edge che il backtest non conferma.
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
