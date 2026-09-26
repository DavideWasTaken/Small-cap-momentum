from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "outputs" / "strategy_decision"
V1 = ROOT / "outputs" / "historical_alpaca"
V2 = ROOT / "outputs" / "v2_candidate"
OUTPUT = ROOT / "outputs" / "strategy_decision_report"


def csv_source(
    source_id: str,
    label: str,
    path: str,
    sql: str,
    filters: list[str],
    definitions: list[str],
    executed_at: str,
) -> dict:
    return {
        "id": source_id,
        "label": label,
        "path": path,
        "query": {
            "engine": "DuckDB",
            "language": "sql",
            "sql": sql,
            "description": f"Query riproducibile sul file {path}.",
            "tables_used": [path],
            "filters": filters,
            "metric_definitions": definitions,
            "executed_at": executed_at,
        },
    }


def main() -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    summary = json.loads((DECISION / "decision_summary.json").read_text(encoding="utf-8"))
    annual = pd.read_csv(DECISION / "v2_annual_100bps.csv").sort_values("year")
    costs = pd.read_csv(DECISION / "v2_cost_sensitivity.csv")
    development = pd.read_csv(DECISION / "candidate_development_audit.csv")
    stability = pd.read_csv(DECISION / "candidate_period_stability.csv")
    v2_gates = pd.read_csv(V2 / "gates.csv")
    bootstrap = pd.read_csv(V2 / "bootstrap.csv")

    comparison = pd.read_csv(DECISION / "comparison_metrics.csv")
    annual["year_label"] = annual.year.astype(str)
    annual["expectancy_display"] = annual.expectancy_filled_pct
    primary_costs = costs[costs.period.eq("primary_2021_2025")].copy()
    primary_costs["cost_label"] = primary_costs.total_cost_bps.astype(int).astype(str) + " bps"
    shadow_costs = costs[costs.period.eq("shadow_2026")].copy()
    gates = v2_gates.copy()
    gates["status"] = gates["pass"].map({True: "Pass", False: "Fail"})
    boot100 = bootstrap[bootstrap.total_cost_bps.eq(100)].iloc[0]

    headline = [
        {
            "candidates_tested": int(summary["candidate_combinations_tested"]),
            "development_passes": int(summary["development_candidates_passing_all_gates"]),
            "stable_candidates": int(summary["candidates_positive_in_all_four_periods"]),
            "v2_gates_passed": int(summary["v2_gates_passed"]),
        }
    ]

    source_summary = {
        "id": "decision_summary",
        "label": "Audit decisionale v1/v2",
        "path": "outputs/strategy_decision/decision_summary.json",
        "query": {
            "engine": "file",
            "language": "json",
            "description": "Metriche riconciliate dai ledger v1 e v2 e verdetto go/no-go.",
            "filters": ["v1 e v2 a 100 bps", "v1 primary 2021–2025", "v2 primary 2021–2025 e shadow 2026"],
            "metric_definitions": [
                "Profit factor = profitti lordi / perdite lorde.",
                "Expectancy = media del rendimento netto per trade.",
                "Mediana = cinquantesimo percentile del rendimento netto per trade.",
            ],
        },
    }
    source_comparison = csv_source(
        "comparison_metrics",
        "Confronto metrico v1/v2",
        "outputs/strategy_decision/comparison_metrics.csv",
        "SELECT * FROM read_csv_auto('outputs/strategy_decision/comparison_metrics.csv');",
        ["v1 e v2 a 100 bps", "v1 primary 2021–2025", "v2 primary 2021–2025 e shadow 2026"],
        [
            "Profit factor = profitti lordi / perdite lorde.",
            "Expectancy = media del rendimento netto per trade.",
            "Mediana = cinquantesimo percentile del rendimento netto per trade.",
        ],
        generated_at,
    )
    source_development = csv_source(
        "development_audit",
        "Audit di selezione sul development",
        "outputs/strategy_decision/candidate_development_audit.csv",
        "SELECT * FROM read_csv_auto('outputs/strategy_decision/candidate_development_audit.csv') ORDER BY development_gate_pass DESC, expectancy_pct DESC;",
        ["period = development_2021_2023", "21 combinazioni strutturali predefinite"],
        ["Pass = almeno 25 trade, PF >= 1.30, expectancy > 0 e mediana > 0."],
        generated_at,
    )
    source_stability = csv_source(
        "period_stability",
        "Stabilità delle 21 combinazioni",
        "outputs/strategy_decision/candidate_period_stability.csv",
        "SELECT * FROM read_csv_auto('outputs/strategy_decision/candidate_period_stability.csv') ORDER BY positive_periods DESC, worst_period_expectancy_pct DESC;",
        ["periods = development 2021–2023, validation 2024, test 2025, shadow 2026"],
        ["Periodo positivo = expectancy > 0 e profit factor > 1."],
        generated_at,
    )
    source_annual = csv_source(
        "v2_annual",
        "Metriche annuali candidata v2",
        "outputs/strategy_decision/v2_annual_100bps.csv",
        "SELECT * FROM read_csv_auto('outputs/strategy_decision/v2_annual_100bps.csv') ORDER BY year;",
        ["total round-trip cost = 100 bps", "setup = strict_resistance", "exit = fixed5_target12"],
        ["Expectancy annuale = media dei rendimenti netti dei trade entrati nell'anno."],
        generated_at,
    )
    source_costs = csv_source(
        "v2_costs",
        "Sensibilità ai costi candidata v2",
        "outputs/strategy_decision/v2_cost_sensitivity.csv",
        "SELECT * FROM read_csv_auto('outputs/strategy_decision/v2_cost_sensitivity.csv') ORDER BY period, total_cost_bps;",
        ["periods = primary_2021_2025 and shadow_2026", "costs = 24, 50, 100, 200 bps"],
        ["Costo round-trip applicato metà all'ingresso e metà all'uscita."],
        generated_at,
    )
    source_gates = csv_source(
        "v2_gates",
        "Gate decisionali candidata v2",
        "outputs/v2_candidate/gates.csv",
        "SELECT * FROM read_csv_auto('outputs/v2_candidate/gates.csv');",
        ["candidate = strict_resistance + fixed5_target12", "primary cost = 100 bps"],
        ["La candidata è promossa solo se tutti i gate passano."],
        generated_at,
    )
    source_quality = {
        "id": "quality",
        "label": "Qualità finestre intraday SIP",
        "path": "outputs/historical_5y/intraday_quality_summary.json",
        "query": {
            "engine": "file",
            "language": "json",
            "description": "Controlli di completezza sulle 301 finestre Alpaca SIP.",
            "filters": ["301 finestre storiche predefinite"],
            "metric_definitions": ["Coverage = sessioni evento presenti / sessioni richieste."],
        },
    }
    sources = [
        source_summary,
        source_comparison,
        source_development,
        source_stability,
        source_annual,
        source_costs,
        source_gates,
        source_quality,
    ]

    cards = [
        {
            "id": "tested",
            "dataset": "headline",
            "sourceId": "development_audit",
            "description": "Sette setup per tre logiche di rischio/uscita.",
            "metrics": [{"label": "Combinazioni testate", "field": "candidates_tested", "format": "number"}],
        },
        {
            "id": "dev_passes",
            "dataset": "headline",
            "sourceId": "development_audit",
            "description": "Combinazioni che superano tutti i gate nel solo 2021–2023.",
            "metrics": [{"label": "Pass sul development", "field": "development_passes", "format": "number"}],
        },
        {
            "id": "stable",
            "dataset": "headline",
            "sourceId": "period_stability",
            "description": "Combinazioni positive in tutte le quattro finestre temporali.",
            "metrics": [{"label": "Candidate stabili", "field": "stable_candidates", "format": "number"}],
        },
        {
            "id": "v2_gate_count",
            "dataset": "headline",
            "sourceId": "v2_gates",
            "description": "Gate passati dalla candidata v2 pubblicata.",
            "metrics": [{"label": "Gate v2 passati su 6", "field": "v2_gates_passed", "format": "number"}],
        },
    ]

    charts = [
        {
            "id": "case_comparison",
            "title": "Expectancy nei tre casi decisionali",
            "subtitle": "Rendimento netto medio per trade; costo round-trip 100 bps",
            "showDescription": True,
            "intent": "comparison",
            "question": "La v2 migliora la v1 e mantiene il risultato nel periodo successivo?",
            "rationale": "Tre barre per confrontare scenari discreti con valori firmati.",
            "type": "horizontalBar",
            "dataset": "comparison",
            "source": source_comparison,
            "layout": "full",
            "valueFormat": "percent",
            "unit": "%",
            "encodings": {
                "x": {"field": "case", "type": "nominal", "label": "Caso"},
                "y": {"field": "expectancy_pct", "type": "quantitative", "format": "percent", "label": "Expectancy netta"},
                "tooltip": [
                    {"field": "trades", "type": "quantitative", "label": "Trade"},
                    {"field": "profit_factor", "type": "quantitative", "label": "Profit factor"},
                    {"field": "median_return_pct", "type": "quantitative", "format": "percent", "label": "Mediana"},
                ],
            },
            "referenceLines": [{"axis": "y", "value": 0, "label": "Pareggio", "color": "neutral"}],
            "settings": {"sort": "ascending", "showValues": True},
            "palette": {"kind": "sequential", "name": "blue"},
            "surface": {"surface": "card", "viewMode": "both"},
        },
        {
            "id": "annual_v2",
            "title": "Expectancy annuale della candidata v2",
            "subtitle": "2021–2026 YTD, costo round-trip 100 bps; campione variabile per anno",
            "showDescription": True,
            "intent": "comparison",
            "question": "Il rendimento della candidata è stabile nel tempo?",
            "rationale": "Barre per sei periodi annuali discreti e campioni piccoli.",
            "type": "bar",
            "dataset": "annual",
            "source": source_annual,
            "layout": "full",
            "valueFormat": "percent",
            "unit": "%",
            "encodings": {
                "x": {"field": "year_label", "type": "ordinal", "label": "Anno"},
                "y": {"field": "expectancy_display", "type": "quantitative", "format": "percent", "label": "Expectancy netta"},
                "tooltip": [
                    {"field": "filled_trades", "type": "quantitative", "label": "Trade"},
                    {"field": "profit_factor", "type": "quantitative", "label": "Profit factor"},
                    {"field": "median_return_pct", "type": "quantitative", "format": "percent", "label": "Mediana"},
                ],
            },
            "referenceLines": [{"axis": "y", "value": 0, "label": "Pareggio", "color": "neutral"}],
            "settings": {"sort": "custom", "showValues": True},
            "palette": {"kind": "sequential", "name": "orange"},
            "surface": {"surface": "card", "viewMode": "both"},
        },
        {
            "id": "cost_v2",
            "title": "Expectancy v2 per costo operativo",
            "subtitle": "2021–2025; quattro scenari discreti di costo round-trip",
            "showDescription": True,
            "intent": "comparison",
            "question": "Quanto margine conserva la v2 all'aumentare dei costi?",
            "rationale": "Barre per scenari discreti; una linea suggerirebbe una granularità non osservata.",
            "type": "bar",
            "dataset": "primary_costs",
            "source": source_costs,
            "layout": "full",
            "valueFormat": "percent",
            "unit": "%",
            "encodings": {
                "x": {"field": "cost_label", "type": "ordinal", "label": "Costo round-trip"},
                "y": {"field": "expectancy_filled_pct", "type": "quantitative", "format": "percent", "label": "Expectancy netta"},
                "tooltip": [
                    {"field": "profit_factor", "type": "quantitative", "label": "Profit factor"},
                    {"field": "median_return_pct", "type": "quantitative", "format": "percent", "label": "Mediana"},
                ],
            },
            "referenceLines": [{"axis": "y", "value": 0, "label": "Pareggio", "color": "neutral"}],
            "settings": {"sort": "custom", "showValues": True},
            "palette": {"kind": "sequential", "name": "blue"},
            "surface": {"surface": "card", "viewMode": "both"},
        },
    ]

    tables = [
        {
            "id": "v2_gate_table",
            "title": "Gate di promozione della candidata v2",
            "subtitle": "Sei criteri decisionali a 100 bps",
            "showDescription": True,
            "dataset": "v2_gates",
            "source": source_gates,
            "layout": "full",
            "density": "spacious",
            "defaultSort": {"field": "gate", "direction": "asc"},
            "columns": [
                {"field": "gate", "label": "Gate", "type": "text"},
                {"field": "observed", "label": "Osservato", "type": "number"},
                {"field": "required", "label": "Richiesto", "type": "text"},
                {"field": "status", "label": "Esito", "type": "text"},
            ],
        }
    ]

    manifest = {
        "version": 1,
        "surface": "report",
        "title": "Small-cap momentum: decisione go/no-go",
        "description": "Audit indipendente e ottimizzazione temporale della strategia v1/v2.",
        "generatedAt": generated_at,
        "sources": sources,
        "cards": cards,
        "charts": charts,
        "tables": tables,
        "blocks": [
            {"id": "title", "type": "markdown", "body": "# Small-cap momentum: decisione go/no-go"},
            {
                "id": "summary",
                "type": "markdown",
                "body": (
                    "## Executive Summary\n\n"
                    "- **Decisione: no-go.** Scartare la formalizzazione v1/v2 come candidata per la produzione e non collegarla a IBKR.\n"
                    "- **La v1 è chiaramente negativa.** Su 83 trade 2021–2025 a 100 bps ha PF 0,741, expectancy -0,782% e mediana -2,392%.\n"
                    "- **La v2 non è una conferma.** Migliora il 2021–2025 a PF 1,395 ed expectancy +0,849%, ma il bootstrap include zero e il 2026 scende a PF 0,434 ed expectancy -1,764%. Zero delle 21 combinazioni testate supera una selezione temporale completa."
                ),
            },
            {"id": "selection_metrics", "type": "metric-strip", "cardIds": ["tested", "dev_passes", "stable", "v2_gate_count"]},
            {
                "id": "comparison_text",
                "type": "markdown",
                "sourceId": "decision_summary",
                "body": (
                    "## La v2 recupera il passato ma perde nel periodo successivo\n\n"
                    "La resistenza più stretta con stop 5% e target 12% trasforma il 2021–2025 da negativo a positivo. Tuttavia la variante è stata individuata dopo l'analisi del campione e il controllo 2026 cambia segno con un deterioramento di 2,61 punti percentuali di expectancy per trade. **Il miglioramento storico è compatibile con selezione ex post, non con un edge stabile.**"
                ),
            },
            {"id": "comparison_chart", "type": "chart", "chartId": "case_comparison", "layout": "full"},
            {
                "id": "selection_text",
                "type": "markdown",
                "sourceId": "development_audit",
                "body": (
                    "## L'ottimizzazione anti-overfitting non seleziona una strategia\n\n"
                    "Sono state provate 21 combinazioni: sette variazioni strutturali per tre logiche di rischio/uscita. Sul solo 2021–2023 nessuna raggiunge insieme almeno 25 trade, PF ≥ 1,30, expectancy positiva e mediana positiva. Inoltre nessuna combinazione è positiva in tutte le finestre 2021–2023, 2024, 2025 e 2026. **Scegliere comunque la migliore sul totale 2021–2025 userebbe il test come training.**"
                ),
            },
            {
                "id": "annual_text",
                "type": "markdown",
                "sourceId": "v2_annual",
                "body": (
                    "## La candidata dipende dal regime 2023–2025\n\n"
                    "La v2 è negativa nel 2021 e 2022, positiva dal 2023 al 2025 e di nuovo nettamente negativa nel 2026. Il risultato primario aggregato nasconde quindi una forte instabilità temporale; tre anni positivi su cinque restano sotto il gate di quattro."
                ),
            },
            {"id": "annual_chart", "type": "chart", "chartId": "annual_v2", "layout": "full"},
            {
                "id": "cost_text",
                "type": "markdown",
                "sourceId": "v2_costs",
                "body": (
                    "## Il margine economico è insufficiente per small-cap live\n\n"
                    "Nel 2021–2025 la v2 resta positiva a 100 bps ma diventa negativa a 200 bps; nel 2026 è negativa in tutti e quattro gli scenari di costo. Il modello non osserva spread, impatto, partial fill, halt o LULD. **Non c'è un cuscinetto prudente per l'esecuzione automatica reale.**"
                ),
            },
            {"id": "cost_chart", "type": "chart", "chartId": "cost_v2", "layout": "full"},
            {
                "id": "gates_text",
                "type": "markdown",
                "sourceId": "v2_gates",
                "body": (
                    f"## La v2 passa soltanto due gate su sei\n\n"
                    f"Passano PF e mediana sul 2021–2025. Falliscono numerosità, limite inferiore bootstrap ({boot100.ci_low_pct:.3%}), stabilità annuale e controllo 2026. La strategia non è pronta neppure per usare il paper trading come presunta conferma di redditività."
                ),
            },
            {"id": "gates_table", "type": "table", "tableId": "v2_gate_table", "layout": "full"},
            {
                "id": "quality_text",
                "type": "markdown",
                "sourceId": "quality",
                "body": (
                    "## I risultati sono riproducibili nel perimetro osservato\n\n"
                    "Il run è stato rigenerato da 301 finestre Alpaca SIP su 301, pari a 373.857 barre 15 minuti e copertura completa di 328 sessioni evento. Zero errori di download, zero timestamp duplicati e 11 test automatici su 11 passati. I ledger riconciliano esattamente le metriche aggregate."
                ),
            },
            {
                "id": "next_steps",
                "type": "markdown",
                "body": (
                    "## Cosa fare adesso\n\n"
                    "1. Archiviare v1 e v2 come esperimenti rifiutati; non costruire ora l'adapter ordini IBKR.\n"
                    "2. Non continuare a ritoccare soglie sullo stesso storico. Una nuova ricerca deve partire da un'ipotesi v3 sostanzialmente diversa, non da un'altra combinazione di parametri.\n"
                    "3. Usare un universo point-in-time con delisted, regole congelate e una finestra realmente non osservata.\n"
                    "4. Richiedere prima del paper trading almeno 100 trade out-of-sample, PF ≥ 1,30 dopo 100 bps, mediana positiva, limite inferiore dell'intervallo sopra zero e almeno quattro anni positivi su cinque.\n"
                    "5. Solo dopo questi gate raccogliere almeno 50 shadow/paper fill su IBKR per misurare spread e slippage reale."
                ),
            },
            {
                "id": "questions",
                "type": "markdown",
                "body": (
                    "## Ulteriori domande\n\n"
                    "- Esiste un filtro causale point-in-time su float, catalyst e liquidità che rappresenti davvero la selezione discrezionale?\n"
                    "- Il pattern ha edge soltanto in regimi di volatilità/momentum identificabili prima dell'ingresso?\n"
                    "- Quote e halt reali peggiorano l'esecuzione oltre lo stress deterministico?\n\n"
                    "Queste domande definiscono una strategia nuova; non sono una giustificazione per promuovere retroattivamente la v2."
                ),
            },
            {
                "id": "caveats",
                "type": "markdown",
                "body": (
                    "## Caveat e assunzioni\n\n"
                    "L'universo deriva da componenti IWM correnti e soffre di survivorship bias; mancano delisted point-in-time, bid/ask, tick path, halt/LULD e un portfolio engine che gestisca posizioni concorrenti. Il bootstrap per trade non dimostra indipendenza. Questi limiti impediscono una conclusione universale sul momentum discrezionale, ma non trasformano i risultati osservati in evidenza sufficiente per il live."
                ),
            },
        ],
    }

    artifact = {
        "surface": "report",
        "manifest": manifest,
        "snapshot": {
            "version": 1,
            "generatedAt": generated_at,
            "status": "ready",
            "datasets": {
                "headline": headline,
                "comparison": comparison.to_dict("records"),
                "annual": annual[
                    ["year", "year_label", "filled_trades", "win_rate", "profit_factor", "expectancy_display", "median_return_pct"]
                ].to_dict("records"),
                "primary_costs": primary_costs[
                    ["cost_label", "total_cost_bps", "filled_trades", "profit_factor", "expectancy_filled_pct", "median_return_pct"]
                ].to_dict("records"),
                "shadow_costs": shadow_costs.to_dict("records"),
                "development_audit": development.head(10).to_dict("records"),
                "period_stability": stability.head(10).to_dict("records"),
                "v2_gates": gates[["gate", "observed", "required", "status"]].to_dict("records"),
            },
        },
        "sources": sources,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "artifact.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(OUTPUT / "artifact.json")


if __name__ == "__main__":
    main()
