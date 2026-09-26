from __future__ import annotations

from pathlib import Path

import nbformat as nbf
import pandas as pd
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "automation_readiness"
NOTEBOOK = ROOT / "notebooks" / "automation_readiness.ipynb"


def current_summary() -> str:
    stress = pd.read_csv(OUTPUT / "execution_stress.csv")
    split = pd.read_csv(OUTPUT / "chronological_split.csv")
    row = stress[(stress.total_cost_bps == 100) & (stress.delay_bars == 0)].iloc[0]
    late = split[split.period == "late_half"].iloc[0]
    return (
        "## tl;dr\n\n"
        "**Non ancora pronto per il live.** Sul campione regular-only di 15 trade, "
        f"a 100 bps il profit factor è {row.profit_factor:.2f}, l'expectancy è "
        f"{row.expectancy_filled_pct:.2%} e la mediana è {row.median_return_pct:.2%}. "
        f"La metà cronologicamente più recente ha expectancy {late.expectancy_filled_pct:.2%}. "
        "La pipeline è adatta al prossimo stadio: IBKR shadow/paper testing con ordini non trasmessi."
    )


def build_notebook() -> None:
    notebook = nbf.v4.new_notebook()
    notebook["metadata"]["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    notebook["cells"] = [
        nbf.v4.new_markdown_cell("# Automation readiness: small-cap continuation"),
        nbf.v4.new_markdown_cell(current_summary()),
        nbf.v4.new_markdown_cell(
            "## Context & Methods\n\n"
            "Obiettivo: decidere se il motore può passare dal backtest a un sistema automatico "
            "su IBKR o MetaTrader. Il test usa solo sessione regolare, target 20%, dati causali e "
            "nessun override di livello.\n\n"
            "### Key Assumptions\n\n"
            "- Capitale di riferimento: 100.000 USD, rischio 1% e posizione massima 25%.\n"
            "- I costi sono stress deterministici, non spread bid/ask osservati.\n"
            "- I risultati sono descrittivi: il campione non è indipendente né out-of-sample."
        ),
        nbf.v4.new_markdown_cell("## Data\n\n### 1. Load cached bars and rerun the battery"),
        nbf.v4.new_code_cell(
            "from pathlib import Path\n"
            "import sys\n"
            "import matplotlib.pyplot as plt\n"
            "import pandas as pd\n\n"
            "ROOT = Path.cwd().resolve().parent if Path.cwd().name == 'notebooks' else Path.cwd().resolve()\n"
            "sys.path.insert(0, str(ROOT / 'src'))\n"
            "from smallcap_bt.config import load_config\n"
            "from smallcap_bt.data import download_universe, provider_from_config, read_tickers\n"
            "from smallcap_bt.robustness import run_readiness_analysis\n\n"
            "cfg = load_config(ROOT / 'configs/iwm_regular_only.yaml')\n"
            "tickers = read_tickers(ROOT / 'outputs/iwm_automated/intraday_candidates.txt')\n"
            "frames, errors = download_universe(tickers, provider_from_config(cfg.data))\n"
            "assert not errors, errors\n"
            "results = run_readiness_analysis(frames, cfg, ROOT / 'outputs/automation_readiness')\n"
            "print({'tickers': len(frames), 'bars': sum(map(len, frames.values()))})"
        ),
        nbf.v4.new_markdown_cell("## Results\n\n### 2. Live-readiness gates"),
        nbf.v4.new_code_cell("results['readiness_scorecard']"),
        nbf.v4.new_markdown_cell(
            "### 3. Cost and latency stress\n\n"
            "The bars compare filled-trade expectancy. Extra 15-minute delay is an outage stress, "
            "not an estimate of normal broker latency."
        ),
        nbf.v4.new_code_cell(
            "stress = results['execution_stress']\n"
            "fig, ax = plt.subplots(figsize=(9, 4.5))\n"
            "for delay, group in stress.groupby('delay_bars'):\n"
            "    ax.plot(group.total_cost_bps, group.expectancy_filled_pct * 100, marker='o', label=f'{delay} extra bars')\n"
            "ax.axhline(0, color='#444444', linewidth=1)\n"
            "ax.set(title='Expectancy under cost and execution-delay stress', xlabel='Total round-trip cost (bps)', ylabel='Mean return per filled trade (%)')\n"
            "ax.legend(frameon=False)\n"
            "ax.grid(axis='y', alpha=.2)\n"
            "plt.show()"
        ),
        nbf.v4.new_markdown_cell(
            "### 4. Parameter sensitivity\n\n"
            "One parameter is changed at a time. Positive averages alone are insufficient; "
            "the production gate also requires profit factor ≥1.30 and a positive median."
        ),
        nbf.v4.new_code_cell(
            "sensitivity = results['parameter_sensitivity'].copy()\n"
            "sensitivity[['scenario', 'filled_trades', 'profit_factor', 'expectancy_filled_pct', 'median_return_pct']]"
        ),
        nbf.v4.new_markdown_cell("### 5. Liquidity and concentration"),
        nbf.v4.new_code_cell(
            "liquidity = results['liquidity_diagnostics'].sort_values('participation_of_15m_volume', ascending=False)\n"
            "liquidity[['ticker', 'shares_at_100k', 'entry_bar_dollar_volume', 'participation_of_15m_volume', 'entry_bar_range_pct']]"
        ),
        nbf.v4.new_markdown_cell("### 6. Temporal stability, uncertainty, and session-definition overlap"),
        nbf.v4.new_code_cell(
            "display(results['chronological_split'])\n"
            "display(results['bootstrap_summary'])\n"
            "display(results['signal_overlap'])"
        ),
        nbf.v4.new_markdown_cell(
            "## Takeaways\n\n"
            "- **Automation logic:** implementable and reproducible.\n"
            "- **Economic robustness:** not demonstrated; the recent half is negative and 100-bps "
            "costs reduce PF below the live threshold.\n"
            "- **Execution:** one signal requires an implausibly high share of its 15-minute volume "
            "at the reference account size.\n"
            "- **Next stage:** IBKR shadow mode, followed by at least 50 paper trades; no live order transmission."
        ),
    ]
    NOTEBOOK.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(notebook, NOTEBOOK)
    client = NotebookClient(notebook, timeout=900, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}})
    client.execute()
    nbf.write(notebook, NOTEBOOK)


if __name__ == "__main__":
    build_notebook()
