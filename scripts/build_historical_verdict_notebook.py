from __future__ import annotations

from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "historical_edge_verdict.ipynb"


def markdown(text: str):
    return nbf.v4.new_markdown_cell(text.strip())


def code(text: str):
    return nbf.v4.new_code_cell(text.strip())


def build() -> None:
    notebook = nbf.v4.new_notebook()
    notebook["metadata"] = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3"},
    }
    notebook["cells"] = [
        markdown(
            """
# Verdetto storico: small-cap momentum continuation v1

## tl;dr

La versione meccanica congelata **non mostra un edge utilizzabile**. Nel periodo
primario 2021–2025, con target +20% e 100 bps di costo round-trip, produce 83
trade, profit factor 0,741, expectancy media -0,782% e mediana -2,392% per trade.
Tutte e quattro le uscite hanno expectancy negativa a 100 bps; solo uno dei
cinque anni è positivo. Il risultato giustifica il rifiuto della v1, non la
conclusione che ogni strategia discrezionale di continuation sia impossibile.
"""
        ),
        markdown(
            """
## Context & Methods

Il notebook è il companion riproducibile del backtest storico Alpaca SIP. Carica
soltanto risultati salvati e ricalcola le metriche chiave dal ledger trade-level;
non chiama API e non legge credenziali.

### Key Assumptions

- Regole e parametri sono quelli di `configs/strategy_v1_frozen.yaml`.
- Il periodo primario è 2021–2025; il 2026 è development e non decide il verdetto.
- Il caso operativo principale usa target +20% e 100 bps round-trip.
- Le varianti di uscita sullo stesso segnale non sono osservazioni indipendenti.
- L'universo deriva dagli attuali componenti IWM: resta survivorship bias.
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
RESULTS = ROOT / "outputs" / "historical_alpaca"
QUALITY = ROOT / "outputs" / "historical_5y" / "intraday_quality_summary.json"

plt.style.use("seaborn-v0_8-whitegrid")
COLORS = {"ink": "#243247", "blue": "#3266a8", "gold": "#c4932f", "open": "#b8c7d9"}
"""
        ),
        markdown("## Data\n\n### 1. Load the saved, bounded outputs"),
        code(
            """
stressed = pd.read_csv(RESULTS / "stressed_trades.csv")
reported = pd.read_csv(RESULTS / "cost_stress_all_variants.csv")
annual = pd.read_csv(RESULTS / "annual_cost_metrics.csv")
bootstrap = pd.read_csv(RESULTS / "bootstrap_primary_all_variants.csv")
checks = pd.read_csv(RESULTS / "validation_checks.csv")
quality = json.loads(QUALITY.read_text(encoding="utf-8"))

stressed["entry_year"] = pd.to_datetime(stressed["entry_time"], utc=True).dt.year
{
    "trade_ledger_rows": len(stressed),
    "saved_result_rows": len(reported),
    "window_quality": quality,
}
"""
        ),
        markdown("### 2. Recompute the decision metrics independently"),
        code(
            """
def summarize(returns: pd.Series) -> dict:
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    return {
        "trades": int(len(returns)),
        "win_rate": float((returns > 0).mean()),
        "profit_factor": float(wins.sum() / -losses.sum()),
        "expectancy": float(returns.mean()),
        "median_return": float(returns.median()),
    }

primary = stressed[stressed["entry_year"] <= 2025]
recomputed = pd.DataFrame([
    {"variant": variant, "total_cost_bps": cost, **summarize(group["return_pct"])}
    for (variant, cost), group in primary.groupby(["variant", "total_cost_bps"])
])

reported_primary = reported[reported["period"] == "primary_2021_2025"].copy()
merged = recomputed.merge(
    reported_primary,
    on=["variant", "total_cost_bps"],
    validate="one_to_one",
)
assert np.allclose(merged["profit_factor_x"], merged["profit_factor_y"], rtol=0, atol=1e-12)
assert np.allclose(merged["expectancy"], merged["expectancy_filled_pct"], rtol=0, atol=1e-12)
assert np.allclose(merged["median_return"], merged["median_return_pct"], rtol=0, atol=1e-12)

target100 = recomputed.query("variant == 'target_20' and total_cost_bps == 100").iloc[0]
target100.to_frame("value")
"""
        ),
        markdown(
            """
## Results

### Tutte le uscite falliscono al costo operativo principale

Il confronto usa gli stessi 83 segnali e cambia soltanto la logica di uscita.
Nessuna variante ha expectancy positiva a 100 bps; quindi il risultato non è
spiegato soltanto dalla scelta del target +20%.
"""
        ),
        code(
            """
exit_100 = (
    recomputed.query("total_cost_bps == 100")
    .sort_values("expectancy")
    .assign(expectancy_pct=lambda x: 100 * x["expectancy"])
)
display(exit_100[["variant", "trades", "win_rate", "profit_factor", "expectancy_pct", "median_return"]])

fig, ax = plt.subplots(figsize=(8.5, 4.5))
ax.barh(exit_100["variant"], exit_100["expectancy_pct"], color=COLORS["blue"], edgecolor=COLORS["ink"])
ax.axvline(0, color=COLORS["ink"], linewidth=1)
ax.set(title="Expectancy per trade per variante di uscita", xlabel="Expectancy netta (%)", ylabel="")
for i, value in enumerate(exit_100["expectancy_pct"]):
    ax.text(value - 0.03, i, f"{value:.2f}%", va="center", ha="right", color="white", fontweight="bold")
plt.tight_layout()
plt.show()
"""
        ),
        markdown(
            """
### Il risultato non è stabile nel tempo

Con target +20% e 100 bps soltanto il 2023 è positivo. I campioni annuali sono
piccoli, ma quattro anni negativi su cinque sono incompatibili con l'ipotesi di
un edge robusto pronto per automazione.
"""
        ),
        code(
            """
annual_target = (
    annual.query("variant == 'target_20' and total_cost_bps == 100 and year <= 2025")
    .sort_values("year")
    .assign(expectancy_pct=lambda x: 100 * x["expectancy_filled_pct"])
)
display(annual_target[["year", "filled_trades", "win_rate", "profit_factor", "expectancy_pct", "median_return_pct"]])

fig, ax = plt.subplots(figsize=(8.5, 4.5))
ax.bar(annual_target["year"].astype(str), annual_target["expectancy_pct"], color=COLORS["gold"], edgecolor=COLORS["ink"])
ax.axhline(0, color=COLORS["ink"], linewidth=1)
ax.set(title="Expectancy annuale: target +20%", xlabel="Anno", ylabel="Expectancy netta (%)")
for i, value in enumerate(annual_target["expectancy_pct"]):
    ax.text(i, value + (0.08 if value >= 0 else -0.08), f"{value:.2f}%", ha="center", va="bottom" if value >= 0 else "top")
plt.tight_layout()
plt.show()
"""
        ),
        markdown(
            """
### L'incertezza non salva il caso base

Il bootstrap non prova che la vera expectancy sia certamente negativa: il 95%
descrittivo include zero. Ma il punto stimato è negativo e nessuno dei sei gate
predefiniti passa. Con evidenza inconclusiva e point estimate sfavorevole, la
decisione prudente è non promuovere la strategia.
"""
        ),
        code(
            """
boot100 = bootstrap.query("variant == 'target_20' and total_cost_bps == 100").iloc[0]
decision_checks = checks[checks["severity"] == "decision"].copy()
display(pd.DataFrame({
    "mean": [boot100["mean_pct"]],
    "95% low": [boot100["ci_low_pct"]],
    "95% high": [boot100["ci_high_pct"]],
}))
display(decision_checks[["check", "observed", "expected", "status"]])
assert (decision_checks["status"] == "FAIL").all()
"""
        ),
        markdown(
            """
## Takeaways

- **Verdetto:** rifiutare la strategia automatica v1; non collegarla a IBKR o MetaTrader.
- Il campione primario è sotto il gate minimo di 100 trade, ma il problema non è
  solo la potenza statistica: PF, expectancy, mediana, stabilità annuale e tutte
  le varianti di uscita puntano nella direzione sbagliata.
- Eventuali modifiche sostanziali costituiscono una v2 e devono essere congelate
  prima di un nuovo test. Ottimizzare sullo stesso 2021–2025 e presentare il
  risultato come conferma creerebbe data-snooping.
- Un test live/paper ha senso solo dopo una nuova evidenza storica positiva e
  indipendente; il paper trading non corregge una strategia già negativa nel backtest.
"""
        ),
    ]

    NOTEBOOK.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(notebook, NOTEBOOK)
    client = NotebookClient(notebook, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}})
    client.execute()
    nbf.write(notebook, NOTEBOOK)
    print(NOTEBOOK)


if __name__ == "__main__":
    build()
