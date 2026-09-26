from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "outputs" / "monthly_momentum"
OUTPUT = ROOT / "outputs" / "monthly_momentum_report"


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
    metrics = pd.read_csv(DATA / "metrics.csv")
    buckets = pd.read_csv(DATA / "bucket_metrics.csv")
    direct_metrics = pd.read_csv(DATA / "direct_metrics.csv")
    direct_equity = pd.read_csv(DATA / "direct_equity.csv", parse_dates=["Date"])
    direct_annual = pd.read_csv(DATA / "direct_annual_returns.csv")
    gates = pd.read_csv(DATA / "direct_gates.csv")
    bootstrap = pd.read_csv(DATA / "bootstrap_vs_xsmo.csv").iloc[0]
    break_even = pd.read_csv(DATA / "cost_break_even.csv")
    turnover_cost_grid = pd.read_csv(DATA / "turnover_cost_grid.csv")
    capital_costs = pd.read_csv(DATA / "capital_cost_scenarios.csv")
    implementation = json.loads(
        (DATA / "implementation_cost_verdict.json").read_text(encoding="utf-8")
    )
    quality = json.loads((DATA / "data_quality.json").read_text(encoding="utf-8"))
    validation = json.loads((DATA / "validation_summary.json").read_text(encoding="utf-8"))

    indexed = direct_metrics.set_index("series")
    small = indexed.loc["Small momentum gross"]
    xsmo = indexed.loc["XSMO"]
    mtum = indexed.loc["MTUM"]
    iwm = indexed.loc["IWM"]
    smallest = indexed.loc["Smallest-quintile momentum gross"]
    cost25 = indexed.loc["Small momentum − 25 bps/month"]

    headline = [{
        "small_cagr": small.cagr,
        "xsmo_cagr": xsmo.cagr,
        "cagr_gap": small.cagr - xsmo.cagr,
        "break_even_cost_bps": implementation["break_even_cost_bps_per_side_at_academic_turnover"],
        "gates_passed": int(gates["pass"].sum()),
    }]

    comparison_names = [
        "Small momentum gross",
        "XSMO",
        "MTUM",
        "IWM",
        "Smallest-quintile momentum gross",
        "Small momentum − 25 bps/month",
    ]
    comparison = direct_metrics[direct_metrics.series.isin(comparison_names)].copy()
    comparison["series"] = pd.Categorical(
        comparison.series, categories=comparison_names, ordered=True
    )
    comparison = comparison.sort_values("series")

    equity_long = direct_equity.melt(
        id_vars="Date",
        value_vars=["Small momentum gross", "XSMO", "MTUM", "IWM"],
        var_name="series",
        value_name="wealth",
    )
    equity_long["Date"] = equity_long.Date.dt.strftime("%Y-%m-%d")

    full_years = direct_annual[direct_annual.Year.between(2020, 2025)].copy()
    full_years["year_label"] = full_years.Year.astype(str)
    full_years["excess_vs_xsmo"] = (
        full_years["Small momentum gross"] - full_years.XSMO
    )

    cost_frame = turnover_cost_grid[
        turnover_cost_grid.turnover_scenario.eq("Academic monthly momentum proxy")
    ].copy()
    cost_frame["cost_label"] = cost_frame.all_in_cost_bps_per_side.astype(int).astype(str) + " bps"
    capital_frame = capital_costs[
        capital_costs.pricing_plan.eq("IBKR Pro Tiered")
        & capital_costs.orders_per_month.eq(120)
    ].copy()
    capital_frame["capital_label"] = "$" + capital_frame.capital_usd.map(lambda value: f"{int(value / 1000)}k")

    gates["status"] = gates["pass"].map({True: "Pass", False: "Fail"})
    buckets["bucket_short"] = ["Low", "Neutral", "High"]

    common_filters = [
        "periodo diretto = 2019-07-31 / 2026-05-31",
        "frequenza = mensile",
        "portafoglio accademico = value weighted",
    ]
    full_filters = [
        "periodo fattore = 2013-05-31 / 2026-05-31",
        "frequenza = mensile",
        "portafoglio accademico = value weighted",
    ]
    return_defs = [
        "Momentum = rendimento cumulato da t−12 a t−2; il mese più recente è escluso.",
        "Small = sotto la mediana NYSE nella specifica primaria 2×3.",
        "CAGR = rendimento composto annualizzato; Sharpe usa il risk-free mensile Fama-French.",
    ]
    source_returns = csv_source(
        "source_returns",
        "Rendimenti mensili allineati",
        "outputs/monthly_momentum/source_returns.csv",
        "SELECT * FROM read_csv_auto('outputs/monthly_momentum/source_returns.csv') ORDER BY Date;",
        full_filters,
        return_defs,
        generated_at,
    )
    source_metrics = csv_source(
        "metrics",
        "Metriche comparative",
        "outputs/monthly_momentum/direct_metrics.csv",
        "SELECT * FROM read_csv_auto('outputs/monthly_momentum/direct_metrics.csv') WHERE series IN ('Small momentum gross', 'XSMO', 'MTUM', 'IWM', 'Smallest-quintile momentum gross', 'Small momentum − 25 bps/month') ORDER BY cagr DESC;",
        full_filters,
        return_defs,
        generated_at,
    )
    source_buckets = csv_source(
        "buckets",
        "Bucket momentum small-cap",
        "outputs/monthly_momentum/bucket_metrics.csv",
        "SELECT *, CASE bucket WHEN 'Small-cap low momentum' THEN 'Low' WHEN 'Small-cap neutral momentum' THEN 'Neutral' ELSE 'High' END AS bucket_short FROM read_csv_auto('outputs/monthly_momentum/bucket_metrics.csv') ORDER BY cagr;",
        common_filters,
        return_defs,
        generated_at,
    )
    source_equity = csv_source(
        "equity",
        "Crescita cumulata di un dollaro",
        "outputs/monthly_momentum/direct_equity.csv",
        "SELECT Date, series, wealth FROM (SELECT Date, \"Small momentum gross\", XSMO, MTUM, IWM FROM read_csv_auto('outputs/monthly_momentum/direct_equity.csv')) UNPIVOT (wealth FOR series IN (\"Small momentum gross\", XSMO, MTUM, IWM)) ORDER BY Date, series;",
        common_filters,
        ["Wealth = prodotto cumulato di 1 + rendimento mensile; base iniziale 1."],
        generated_at,
    )
    source_annual = csv_source(
        "annual",
        "Rendimenti annuali",
        "outputs/monthly_momentum/direct_annual_returns.csv",
        "SELECT *, CAST(Year AS VARCHAR) AS year_label, \"Small momentum gross\" - XSMO AS excess_vs_xsmo FROM read_csv_auto('outputs/monthly_momentum/direct_annual_returns.csv') WHERE Year BETWEEN 2020 AND 2025 ORDER BY Year;",
        ["anni completi = 2020–2025"],
        ["Excess vs XSMO = rendimento annuo small momentum lordo meno rendimento annuo XSMO."],
        generated_at,
    )
    source_costs = csv_source(
        "costs",
        "CAGR netto per costo e turnover",
        "outputs/monthly_momentum/turnover_cost_grid.csv",
        "SELECT *, CAST(all_in_cost_bps_per_side AS VARCHAR) || ' bps' AS cost_label FROM read_csv_auto('outputs/monthly_momentum/turnover_cost_grid.csv') WHERE turnover_scenario = 'Academic monthly momentum proxy' ORDER BY all_in_cost_bps_per_side;",
        common_filters + ["turnover annuo one-way = 305%", "costo all-in per lato = 5–100 bps"],
        [
            "Drag annuo = turnover one-way × 2 lati × costo all-in per lato.",
            "CAGR netto è calcolato sottraendo dal rendimento mensile il drag annuo equivalente.",
        ],
        generated_at,
    )
    source_capital = csv_source(
        "capital_costs",
        "Costi per scala del capitale",
        "outputs/monthly_momentum/capital_cost_scenarios.csv",
        "SELECT *, '$' || CAST(CAST(capital_usd / 1000 AS INTEGER) AS VARCHAR) || 'k' AS capital_label FROM read_csv_auto('outputs/monthly_momentum/capital_cost_scenarios.csv') WHERE pricing_plan = 'IBKR Pro Tiered' AND orders_per_month = 120 ORDER BY capital_usd;",
        common_filters + [
            "IBKR Pro Tiered: minimo USD 0,35 per ordine",
            "120 ordini/mese",
            "turnover annuo one-way = 305%",
            "costo di mercato all-in = 25 bps per lato",
        ],
        [
            "Costo totale prima delle imposte = spread/slippage proxy + minimi per ordine.",
            "La stima non include fee regolamentari, impatto non lineare o fiscalità.",
        ],
        generated_at,
    )
    source_break_even = csv_source(
        "break_even",
        "Costo di pareggio per turnover",
        "outputs/monthly_momentum/cost_break_even.csv",
        "SELECT * FROM read_csv_auto('outputs/monthly_momentum/cost_break_even.csv') WHERE turnover_scenario = 'Academic monthly momentum proxy';",
        common_filters + ["turnover annuo one-way = 305%"],
        ["Break-even = costo per lato che porta il CAGR netto al CAGR osservato di XSMO."],
        generated_at,
    )
    source_implementation = {
        "id": "implementation",
        "label": "Verdetto economico di implementazione",
        "path": "outputs/monthly_momentum/implementation_cost_verdict.json",
        "query": {
            "engine": "file",
            "language": "json",
            "description": "Soglia di pareggio, assunzioni IBKR, caveat fiscali e decisione live.",
            "filters": common_filters + ["turnover accademico proxy = 305% annuo one-way"],
            "metric_definitions": [
                "Break-even = costo per lato che porta il CAGR netto al CAGR osservato di XSMO.",
                "Live-ready richiede costi e turnover osservati, non soltanto proxy letterari.",
            ],
        },
    }
    source_gates = csv_source(
        "gates",
        "Gate decisionali",
        "outputs/monthly_momentum/direct_gates.csv",
        "SELECT * FROM read_csv_auto('outputs/monthly_momentum/direct_gates.csv');",
        common_filters,
        ["Promozione = evidenza competitiva e robusta rispetto a XSMO dopo costi."],
        generated_at,
    )
    source_bootstrap = csv_source(
        "bootstrap",
        "Bootstrap small momentum meno XSMO",
        "outputs/monthly_momentum/bootstrap_vs_xsmo.csv",
        "SELECT * FROM read_csv_auto('outputs/monthly_momentum/bootstrap_vs_xsmo.csv');",
        ["20.000 ricampionamenti", "blocchi circolari da 12 mesi", "seed = 20260712"],
        ["Intervallo al 95% sulla differenza media mensile, annualizzata aritmeticamente."],
        generated_at,
    )
    source_quality = {
        "id": "quality",
        "label": "Qualità e provenienza dati",
        "path": "outputs/monthly_momentum/data_quality.json",
        "query": {
            "engine": "file",
            "language": "json",
            "description": "Controlli di completezza, date, hash e provenienza delle serie.",
            "filters": common_filters,
            "metric_definitions": [
                "Portafogli: Kenneth French Data Library, release CRSP 202605.",
                "ETF: adjusted close Yahoo Finance; XSMO riconciliato con il rendimento NAV YTD Invesco.",
                "Mandato XSMO corrente: S&P SmallCap 600 Momentum Index dal 21 giugno 2019.",
                "Expense ratio totale XSMO: 0,36% secondo la pagina ufficiale Invesco.",
            ],
        },
    }
    sources = [
        source_returns,
        source_metrics,
        source_buckets,
        source_equity,
        source_annual,
        source_costs,
        source_capital,
        source_break_even,
        source_implementation,
        source_gates,
        source_bootstrap,
        source_quality,
    ]

    cards = [
        {
            "id": "small_cagr",
            "dataset": "headline",
            "sourceId": "metrics",
            "description": "Portafoglio small/high momentum accademico, prima dei costi.",
            "metrics": [{"label": "CAGR small momentum", "field": "small_cagr", "format": "percent"}],
        },
        {
            "id": "xsmo_cagr",
            "dataset": "headline",
            "sourceId": "metrics",
            "description": "ETF small-cap momentum investibile nel medesimo intervallo.",
            "metrics": [{"label": "CAGR XSMO", "field": "xsmo_cagr", "format": "percent"}],
        },
        {
            "id": "gap",
            "dataset": "headline",
            "sourceId": "metrics",
            "description": "Differenza annualizzata small momentum lordo meno XSMO.",
            "metrics": [{"label": "Gap lordo vs XSMO", "field": "cagr_gap", "format": "percent"}],
        },
        {
            "id": "break_even_cost",
            "dataset": "headline",
            "sourceId": "break_even",
            "description": "Massimo costo all-in per lato, prima delle imposte, al turnover proxy del 305%.",
            "metrics": [{"label": "Break-even costo/lato", "field": "break_even_cost_bps", "format": "number", "unit": "bps"}],
        },
    ]

    charts = [
        {
            "id": "bucket_cagr",
            "title": "CAGR dei bucket small-cap momentum",
            "subtitle": "Portafogli value weighted 2×3; maggio 2013–maggio 2026",
            "showDescription": True,
            "intent": "comparison",
            "question": "Il segnale ordina correttamente loser, neutral e winner?",
            "rationale": "Tre barre confrontano categorie discrete dello stesso universo.",
            "type": "bar",
            "dataset": "buckets",
            "source": source_buckets,
            "layout": "full",
            "valueFormat": "percent",
            "encodings": {
                "x": {"field": "bucket_short", "type": "ordinal", "label": "Bucket momentum"},
                "y": {"field": "cagr", "type": "quantitative", "format": "percent", "label": "CAGR"},
                "tooltip": [
                    {"field": "sharpe", "type": "quantitative", "label": "Sharpe"},
                    {"field": "max_drawdown", "type": "quantitative", "format": "percent", "label": "Max drawdown"},
                ],
            },
            "settings": {"sort": "custom", "showValues": True},
            "palette": {"kind": "sequential", "name": "blue"},
            "surface": {"surface": "card", "viewMode": "both"},
        },
        {
            "id": "wealth_trend",
            "title": "Crescita cumulata di un dollaro",
            "subtitle": "Rendimenti mensili reinvestiti; small momentum lordo",
            "showDescription": True,
            "intent": "trend",
            "question": "Come evolvono nel tempo small momentum, XSMO, MTUM e IWM?",
            "rationale": "Una linea per serie rende leggibili traiettoria e drawdown lungo 83 mesi comparabili.",
            "type": "line",
            "dataset": "equity_long",
            "source": source_equity,
            "layout": "full",
            "encodings": {
                "x": {"field": "Date", "type": "temporal", "label": "Mese"},
                "y": {"field": "wealth", "type": "quantitative", "label": "Valore di $1"},
                "color": {"field": "series", "type": "nominal", "label": "Serie"},
                "tooltip": [
                    {"field": "series", "type": "nominal", "label": "Serie"},
                    {"field": "wealth", "type": "quantitative", "label": "Valore"},
                ],
            },
            "palette": {"kind": "categorical", "name": "default"},
            "legend": {"position": "bottom", "interactive": True},
            "surface": {"surface": "card", "viewMode": "both"},
        },
        {
            "id": "annual_excess",
            "title": "Extra-rendimento annuale rispetto a XSMO",
            "subtitle": "Anni completi 2020–2025; valori sopra zero indicano vittoria small momentum",
            "showDescription": True,
            "intent": "comparison",
            "question": "L'outperformance rispetto a XSMO è stabile anno per anno?",
            "rationale": "Barre firmate mostrano direttamente frequenza e ampiezza delle vittorie annuali.",
            "type": "bar",
            "dataset": "annual_excess",
            "source": source_annual,
            "layout": "full",
            "valueFormat": "percent",
            "encodings": {
                "x": {"field": "year_label", "type": "ordinal", "label": "Anno"},
                "y": {"field": "excess_vs_xsmo", "type": "quantitative", "format": "percent", "label": "Small meno XSMO"},
                "tooltip": [
                    {"field": "Small momentum gross", "type": "quantitative", "format": "percent", "label": "Small momentum"},
                    {"field": "XSMO", "type": "quantitative", "format": "percent", "label": "XSMO"},
                ],
            },
            "referenceLines": [{"axis": "y", "value": 0, "label": "Pareggio", "color": "neutral"}],
            "settings": {"sort": "custom", "showValues": False},
            "palette": {"kind": "diverging", "name": "redBlue", "midpoint": 0},
            "surface": {"surface": "card", "viewMode": "both"},
        },
        {
            "id": "cost_cagr",
            "title": "CAGR netto per costo di esecuzione",
            "subtitle": "Turnover proxy 305% annuo one-way; XSMO come soglia di confronto",
            "showDescription": True,
            "intent": "comparison",
            "question": "Quale costo per lato annulla il vantaggio lordo su XSMO?",
            "rationale": "La griglia lega esplicitamente turnover, costo per lato e CAGR netto.",
            "type": "bar",
            "dataset": "costs",
            "source": source_costs,
            "layout": "full",
            "valueFormat": "percent",
            "encodings": {
                "x": {"field": "cost_label", "type": "ordinal", "label": "Costo all-in per lato"},
                "y": {"field": "net_cagr", "type": "quantitative", "format": "percent", "label": "CAGR netto"},
                "tooltip": [
                    {"field": "annual_trading_drag", "type": "quantitative", "format": "percent", "label": "Drag annuo"},
                    {"field": "net_sharpe", "type": "quantitative", "label": "Sharpe netto"},
                    {"field": "cagr_gap_vs_xsmo", "type": "quantitative", "format": "percent", "label": "Gap vs XSMO"},
                ],
            },
            "referenceLines": [{"axis": "y", "value": float(xsmo.cagr), "label": "CAGR XSMO", "color": "neutral"}],
            "settings": {"sort": "custom", "showValues": True},
            "palette": {"kind": "sequential", "name": "orange"},
            "surface": {"surface": "card", "viewMode": "both"},
        },
        {
            "id": "capital_gap",
            "title": "Vantaggio netto su XSMO per capitale",
            "subtitle": "IBKR Pro Tiered, 120 ordini/mese, 25 bps/lato e turnover annuo one-way 305%",
            "showDescription": True,
            "intent": "comparison",
            "question": "I minimi per ordine lasciano un vantaggio economico a una scala retail?",
            "rationale": "Le barre mostrano il gap di CAGR dopo costi per cinque livelli di capitale.",
            "type": "bar",
            "dataset": "capital_costs",
            "source": source_capital,
            "layout": "full",
            "valueFormat": "percent",
            "encodings": {
                "x": {"field": "capital_label", "type": "ordinal", "label": "Capitale"},
                "y": {"field": "cagr_gap_vs_xsmo", "type": "quantitative", "format": "percent", "label": "CAGR netto meno XSMO"},
                "tooltip": [
                    {"field": "annual_minimum_commissions_usd", "type": "quantitative", "label": "Minimi annui USD"},
                    {"field": "annual_total_drag_before_tax", "type": "quantitative", "format": "percent", "label": "Drag totale"},
                    {"field": "net_cagr", "type": "quantitative", "format": "percent", "label": "CAGR netto"},
                ],
            },
            "referenceLines": [{"axis": "y", "value": 0, "label": "Pareggio con XSMO", "color": "neutral"}],
            "settings": {"sort": "custom", "showValues": True},
            "palette": {"kind": "diverging", "name": "redBlue", "midpoint": 0},
            "surface": {"surface": "card", "viewMode": "both"},
        },
    ]

    tables = [
        {
            "id": "comparison_table",
            "title": "Metriche comparabili",
            "subtitle": "83 mesi da luglio 2019; portafogli accademici lordi, ETF su adjusted close",
            "showDescription": True,
            "dataset": "comparison",
            "source": source_metrics,
            "layout": "full",
            "density": "spacious",
            "defaultSort": {"field": "cagr", "direction": "desc"},
            "columns": [
                {"field": "series", "label": "Serie", "type": "text"},
                {"field": "cagr", "label": "CAGR", "format": "percent", "movement": True},
                {"field": "annualized_volatility", "label": "Volatilità", "format": "percent"},
                {"field": "sharpe", "label": "Sharpe", "format": "number"},
                {"field": "max_drawdown", "label": "Max DD", "format": "percent", "movement": True},
                {"field": "total_return", "label": "Rendimento totale", "format": "percent", "movement": True},
            ],
        },
        {
            "id": "capital_table",
            "title": "Economia per scala del conto",
            "subtitle": "Scenario IBKR Tiered con 120 ordini/mese; valori prima delle imposte",
            "showDescription": True,
            "dataset": "capital_costs",
            "source": source_capital,
            "layout": "full",
            "density": "spacious",
            "defaultSort": {"field": "capital_usd", "direction": "asc"},
            "columns": [
                {"field": "capital_usd", "label": "Capitale USD", "format": "number"},
                {"field": "annual_minimum_commissions_usd", "label": "Minimi annui USD", "format": "number"},
                {"field": "annual_total_drag_before_tax", "label": "Drag totale", "format": "percent"},
                {"field": "net_cagr", "label": "CAGR netto", "format": "percent"},
                {"field": "cagr_gap_vs_xsmo", "label": "Gap vs XSMO", "format": "percent", "movement": True},
                {"field": "beats_xsmo", "label": "Batte XSMO", "type": "boolean"},
            ],
        },
        {
            "id": "gates_table",
            "title": "Gate decisionali",
            "subtitle": "Tre criteri su sette sono superati; i costi e il bootstrap restano contrari",
            "showDescription": True,
            "dataset": "gates",
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
        },
    ]

    manifest = {
        "version": 1,
        "surface": "report",
        "title": "Small-cap momentum: costi e confronto con XSMO",
        "description": "Verifica economica del portafoglio accademico rispetto a XSMO, incluse commissioni IBKR e turnover.",
        "generatedAt": generated_at,
        "sources": sources,
        "cards": cards,
        "charts": charts,
        "tables": tables,
        "blocks": [
            {"id": "title", "type": "markdown", "body": "# Small-cap momentum: costi e confronto con XSMO"},
            {
                "id": "summary",
                "type": "markdown",
                "body": (
                    "## Executive Summary\n\n"
                    "- **Risposta operativa: oggi non conviene automatizzare questa versione su IBKR; preferire XSMO.** Il portafoglio accademico produce CAGR lordo 16,92% contro 14,10%, ma il margine è soltanto 2,82 punti annui.\n"
                    "- **Al turnover accademico proxy del 305% annuo one-way, il costo massimo sostenibile è 40,4 bps per lato, prima delle imposte.** A 50 bps per lato il CAGR netto stimato scende al 13,44%, già sotto XSMO.\n"
                    "- **La scala retail peggiora il risultato.** Con 120 ordini/mese, IBKR Tiered e 25 bps per lato, $50k restano leggermente sotto XSMO; $100k lo superano di appena 0,49 punti, prima di fee omesse e fiscalità. Il bootstrap lordo include zero."
                ),
            },
            {"id": "headline", "type": "metric-strip", "cardIds": ["small_cagr", "xsmo_cagr", "gap", "break_even_cost"]},
            {
                "id": "method",
                "type": "markdown",
                "sourceId": "quality",
                "body": (
                    "## Cosa abbiamo testato\n\n"
                    "Ogni fine mese il portafoglio compra azioni sotto la mediana di capitalizzazione e nel tercile più alto del rendimento cumulato da t−12 a t−2, escludendo l'ultimo mese. La versione primaria usa i sei portafogli Size × Prior Return della Kenneth French Data Library; la sensibilità restringe l'universo al quintile di size più piccolo. XSMO è il benchmark diretto, ma il ticker segue l'attuale S&P SmallCap 600 Momentum Index soltanto dal 21 giugno 2019: il confronto equo parte quindi da luglio 2019."
                ),
            },
            {
                "id": "bucket_text",
                "type": "markdown",
                "sourceId": "buckets",
                "body": (
                    "## Il fattore ordina correttamente le small cap\n\n"
                    "CAGR e Sharpe salgono dal bucket low al neutral e poi all'high momentum: 6,75%, 11,76% e 14,23% di CAGR. **Questo è il risultato positivo dell'esperimento:** la regola accademica cattura un premio cross-sectional nello stesso universo."
                ),
            },
            {"id": "bucket_chart", "type": "chart", "chartId": "bucket_cagr", "layout": "full"},
            {
                "id": "wealth_text",
                "type": "markdown",
                "sourceId": "equity",
                "body": (
                    "## Il lordo supera XSMO, ma assume più rischio\n\n"
                    "Da luglio 2019 un dollaro cresce a 2,95 nel portafoglio small momentum lordo e a 2,49 in XSMO. Il vantaggio di CAGR è 2,82 punti e lo Sharpe è più alto di 0,080; in cambio, il drawdown massimo è peggiore di 4,18 punti. MTUM resta il migliore sullo Sharpe, ma non è un benchmark small-cap puro."
                ),
            },
            {"id": "wealth_chart_block", "type": "chart", "chartId": "wealth_trend", "layout": "full"},
            {"id": "comparison_table_block", "type": "table", "tableId": "comparison_table", "layout": "full"},
            {
                "id": "annual_text",
                "type": "markdown",
                "sourceId": "annual",
                "body": (
                    "## Il vantaggio annuale è frequente ma non conclusivo\n\n"
                    "Negli anni completi 2020–2025 la strategia lorda batte XSMO in 5 anni su 6. Il 2023 è l'eccezione più importante: XSMO rende 21,55% contro 13,68% del portafoglio accademico. La frequenza è promettente, ma non misura costi o capacità."
                ),
            },
            {"id": "annual_chart_block", "type": "chart", "chartId": "annual_excess", "layout": "full"},
            {
                "id": "bootstrap_text",
                "type": "markdown",
                "sourceId": "bootstrap",
                "body": (
                    "### L'incertezza statistica include sia perdita sia vantaggio\n\n"
                    "La differenza media annualizzata small momentum meno XSMO è +2,85 punti percentuali. Il bootstrap a blocchi dà un intervallo al 95% da -3,32 a +10,23 punti: il campione non esclude che il vantaggio osservato sia rumore."
                ),
            },
            {
                "id": "cost_text",
                "type": "markdown",
                "sourceId": "implementation",
                "body": (
                    "## Il budget di costo è circa 40 bps per lato\n\n"
                    "Con turnover annuo one-way del 305%, il pareggio con XSMO avviene a 40,4 bps all-in per lato. A 25 bps il CAGR netto stimato è 15,17%, ancora 1,07 punti sopra XSMO; a 50 bps scende al 13,44%, 0,66 punti sotto. Questa è già una soglia severa perché deve assorbire commissioni, spread, slippage e impatto, prima delle imposte."
                ),
            },
            {"id": "cost_chart_block", "type": "chart", "chartId": "cost_cagr", "layout": "full"},
            {
                "id": "capital_text",
                "type": "markdown",
                "sourceId": "capital_costs",
                "body": (
                    "## I minimi per ordine consumano il vantaggio sui conti piccoli\n\n"
                    "Nello scenario illustrativo con 120 ordini al mese, pricing IBKR Pro Tiered e 25 bps per lato, i soli minimi valgono $504 l'anno. Con $10k il drag totale stimato è 6,57% e il CAGR netto 9,55%; con $50k il CAGR è 14,02%, 0,08 punti sotto XSMO. Il primo capitale testato sopra il benchmark è $100k, ma il vantaggio è appena 0,49 punti e non remunera bene errore di stima, fee regolamentari, fiscalità o maggiore complessità."
                ),
            },
            {"id": "capital_chart_block", "type": "chart", "chartId": "capital_gap", "layout": "full"},
            {"id": "capital_table_block", "type": "table", "tableId": "capital_table", "layout": "full"},
            {
                "id": "gate_text",
                "type": "markdown",
                "sourceId": "gates",
                "body": (
                    "## Il candidato passa tre gate su sette\n\n"
                    "Passano CAGR lordo, Sharpe lordo e maggioranza degli anni contro XSMO. Falliscono drawdown, confronto dopo lo stress costi originario, sensibilità sul quintile più piccolo e limite inferiore bootstrap. La verifica economica aggiuntiva non cambia il verdetto: senza turnover e fill osservati non c'è margine sufficiente per il live."
                ),
            },
            {"id": "gates_block", "type": "table", "tableId": "gates_table", "layout": "full"},
            {
                "id": "quality_text",
                "type": "markdown",
                "sourceId": "quality",
                "body": (
                    f"## Qualità dei dati\n\n"
                    f"Il dataset contiene {quality['months']} mesi, zero valori mancanti e zero mesi duplicati; il confronto diretto usa 83 mesi. I portafogli accademici provengono dalla release CRSP 202605. Il rendimento XSMO da inizio 2026 a maggio è stato riconciliato entro 0,10 punti percentuali con il NAV ufficiale Invesco. La validazione indipendente passa {validation['checks']} controlli su {validation['checks']}."
                ),
            },
            {
                "id": "next_steps",
                "type": "markdown",
                "body": (
                    "## Cosa fare adesso\n\n"
                    "1. **Non investire ora nello sviluppo dell'automazione IBKR per questa versione; usare XSMO se si vuole l'esposizione small-cap momentum.**\n"
                    "2. Riaprire la ricerca soltanto se si vuole studiare una variante a turnover ridotto: componenti point-in-time, delisted, vincoli ADV, spread e turnover effettivo.\n"
                    "3. Richiedere costi all-in osservati sotto 40,4 bps per lato e un vantaggio netto con cuscinetto, non il solo pareggio.\n"
                    "4. Solo dopo, fare paper trading con fill IBKR e confrontare il percorso netto con XSMO; nessun capitale live finché il risultato non è confermato."
                ),
            },
            {
                "id": "questions",
                "type": "markdown",
                "body": (
                    "## Ulteriori domande\n\n"
                    "- Una regola con bande di ribilanciamento o permanenza minima riduce il turnover senza distruggere il segnale?\n"
                    "- Un filtro di liquidità o una ponderazione inversa alla volatilità riduce il drawdown senza perdere il premio?\n"
                    "- Il vantaggio persiste su un universo S&P 600 point-in-time, più vicino a XSMO rispetto ai breakpoint French?"
                ),
            },
            {
                "id": "caveats",
                "type": "markdown",
                "sourceId": "implementation",
                "body": (
                    "## Caveat e assunzioni\n\n"
                    "I rendimenti Kenneth French sono portafogli accademici lordi, non ordini simulati; il 305% è un proxy di letteratura, non il turnover osservato di questo portafoglio long-only. Il costo di mercato di 25 bps per lato e 60/120 ordini mensili sono scenari, non preventivi. I minimi IBKR escludono fee di terzi, impatto e costi di dati. La definizione small NYSE/CRSP non coincide con l'S&P 600; XSMO usa una costruzione diversa e ribilancia semestralmente. Il percorso adjusted-close di XSMO incorpora il fondo, il cui expense ratio ufficiale è 0,36% e il turnover fiscale riportato è 115%; i costi di transazione interni non sono inclusi nell'expense ratio ma sono già riflessi nel rendimento osservato. Per un residente fiscale italiano le plusvalenze realizzate sono generalmente soggette al 26%, ma il differenziale fiscale non è quantificabile senza regime, lotti, minusvalenze e distribuzioni. Lo storico XSMO precedente al 21 giugno 2019 è escluso perché riflette indici differenti."
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
                "buckets": buckets.to_dict("records"),
                "equity_long": equity_long.to_dict("records"),
                "annual_excess": full_years.to_dict("records"),
                "costs": cost_frame.to_dict("records"),
                "capital_costs": capital_frame.to_dict("records"),
                "gates": gates[["gate", "observed", "required", "status"]].to_dict("records"),
            },
        },
        "sources": sources,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    artifact_path = OUTPUT / "artifact.json"
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    report_notes = {
        "audience": "product stakeholders",
        "delivery_mode": "html",
        "required_structure": {
            "title": "title",
            "executive_summary": "summary",
            "key_findings_with_visual_evidence": [
                "bucket_text",
                "wealth_text",
                "annual_text",
                "cost_text",
                "capital_text",
                "gate_text",
            ],
            "recommended_next_steps": "next_steps",
            "further_questions": "questions",
            "caveats_and_assumptions": "caveats",
        },
        "chart_map": [
            {
                "section": "Il fattore ordina correttamente le small cap",
                "question": "Il segnale ordina loser, neutral e winner?",
                "family": "comparison",
                "type": "bar",
                "fields": ["bucket_short", "cagr"],
                "claim": "Il CAGR cresce monotonicamente con il bucket momentum.",
            },
            {
                "section": "Il lordo supera XSMO, ma assume più rischio",
                "question": "Come evolvono le quattro strategie nel periodo diretto?",
                "family": "trend",
                "type": "line",
                "fields": ["Date", "wealth", "series"],
                "claim": "Il portafoglio lordo termina sopra XSMO, con traiettoria più volatile.",
            },
            {
                "section": "Il vantaggio annuale è frequente ma non conclusivo",
                "question": "Quante volte il portafoglio batte XSMO per anno?",
                "family": "comparison",
                "type": "bar",
                "fields": ["year_label", "excess_vs_xsmo"],
                "claim": "Il portafoglio batte XSMO in cinque anni completi su sei.",
            },
            {
                "section": "Il budget di costo è circa 40 bps per lato",
                "question": "Quale costo per lato annulla il vantaggio lordo?",
                "family": "comparison",
                "type": "bar",
                "fields": ["cost_label", "net_cagr"],
                "claim": "A 305% di turnover il pareggio avviene a circa 40,4 bps per lato.",
            },
            {
                "section": "I minimi per ordine consumano il vantaggio sui conti piccoli",
                "question": "A quale scala il conto supera XSMO nello scenario IBKR?",
                "family": "comparison",
                "type": "bar",
                "fields": ["capital_label", "cagr_gap_vs_xsmo"],
                "claim": "$50k restano sotto XSMO; $100k hanno soltanto 0,49 punti di vantaggio prima delle imposte.",
            },
        ],
        "omissions": [],
    }
    (OUTPUT / "report_notes.json").write_text(
        json.dumps(report_notes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(artifact_path)


if __name__ == "__main__":
    main()
