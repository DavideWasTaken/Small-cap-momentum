from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "outputs" / "historical_alpaca"
OUTPUT = ROOT / "outputs" / "historical_report"


def sql_source(source_id: str, label: str, path: str, sql: str, filters: list[str], definitions: list[str]):
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
            "executed_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def main() -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    independent = pd.read_csv(RESULTS / "independent_primary_metrics.csv")
    annual = pd.read_csv(RESULTS / "annual_cost_metrics.csv")
    bootstrap = pd.read_csv(RESULTS / "bootstrap_primary_all_variants.csv")
    checks = pd.read_csv(RESULTS / "validation_checks.csv")

    exit_100 = independent[independent.total_cost_bps.eq(100)].copy()
    exit_100["variant_label"] = exit_100.variant.map(
        {"target_20": "Target +20%", "target_25": "Target +25%", "trailing": "Trailing stop", "eod": "Fine giornata"}
    )
    exit_100 = exit_100.sort_values("expectancy_pct")
    cost_target = independent[independent.variant.eq("target_20")].sort_values("total_cost_bps").copy()
    cost_target["cost_label"] = cost_target.total_cost_bps.astype(int).astype(str) + " bps"
    annual_target = annual[
        annual.variant.eq("target_20") & annual.total_cost_bps.eq(100) & annual.year.le(2025)
    ].sort_values("year").copy()
    annual_target["year_label"] = annual_target.year.astype(str)
    decision = checks[checks.severity.eq("decision")].copy()
    decision["status_label"] = decision.status.map({"PASS": "Pass", "FAIL": "Fail"})

    target = exit_100[exit_100.variant.eq("target_20")].iloc[0]
    boot = bootstrap[bootstrap.variant.eq("target_20") & bootstrap.total_cost_bps.eq(100)].iloc[0]

    source_metrics = sql_source(
        "primary_metrics",
        "Metriche indipendenti 2021–2025",
        "outputs/historical_alpaca/independent_primary_metrics.csv",
        "SELECT * FROM read_csv_auto('outputs/historical_alpaca/independent_primary_metrics.csv') WHERE total_cost_bps = 100 ORDER BY expectancy_pct;",
        ["entry year <= 2025", "total round-trip cost = 100 bps"],
        [
            "Profit factor = somma rendimenti positivi / valore assoluto della somma dei rendimenti negativi.",
            "Expectancy = media aritmetica del rendimento netto per trade.",
            "Mediana = cinquantesimo percentile del rendimento netto per trade.",
        ],
    )
    source_annual = sql_source(
        "annual_metrics",
        "Metriche annuali target +20%",
        "outputs/historical_alpaca/annual_cost_metrics.csv",
        "SELECT * FROM read_csv_auto('outputs/historical_alpaca/annual_cost_metrics.csv') WHERE variant = 'target_20' AND total_cost_bps = 100 AND year <= 2025 ORDER BY year;",
        ["variant = target_20", "year <= 2025", "total round-trip cost = 100 bps"],
        ["Expectancy annuale = media del rendimento netto dei trade entrati nell'anno."],
    )
    source_bootstrap = sql_source(
        "bootstrap",
        "Bootstrap dell'expectancy primaria",
        "outputs/historical_alpaca/bootstrap_primary_all_variants.csv",
        "SELECT * FROM read_csv_auto('outputs/historical_alpaca/bootstrap_primary_all_variants.csv') WHERE variant = 'target_20' AND total_cost_bps = 100;",
        ["period = primary_2021_2025", "variant = target_20", "total round-trip cost = 100 bps"],
        ["Intervallo descrittivo 95% da 20.000 ricampionamenti bootstrap dei rendimenti per trade."],
    )
    source_checks = sql_source(
        "decision_checks",
        "Gate decisionali e riconciliazioni",
        "outputs/historical_alpaca/validation_checks.csv",
        "SELECT * FROM read_csv_auto('outputs/historical_alpaca/validation_checks.csv') WHERE severity = 'decision';",
        ["severity = decision"],
        ["Un gate passa solo se la soglia congelata è soddisfatta."],
    )
    source_quality = {
        "id": "quality",
        "label": "Qualità finestre intraday SIP",
        "path": "outputs/historical_5y/intraday_quality_summary.json",
        "query": {
            "engine": "file",
            "language": "json",
            "description": "Riepilogo dei controlli sulle finestre 15 minuti Alpaca SIP.",
            "filters": ["301 finestre storiche predefinite"],
            "metric_definitions": ["Coverage = sessioni evento presenti / sessioni evento richieste."],
        },
    }
    source_spec = {
        "id": "frozen_spec",
        "label": "Specifica strategia v1 congelata",
        "path": "FROZEN_SPEC_V1.md",
        "query": {"engine": "file", "language": "markdown", "description": "Regole e gate fissati prima del run SIP pluriennale."},
    }
    sources = [source_metrics, source_annual, source_bootstrap, source_checks, source_quality, source_spec]

    headline = [{
        "trades": int(target.trades),
        "profit_factor": float(target.profit_factor),
        "expectancy": float(target.expectancy_pct),
        "median_return": float(target.median_return_pct),
        "positive_years": int((annual_target.expectancy_filled_pct > 0).sum()),
    }]

    exit_rows = exit_100[["variant_label", "trades", "win_rate", "profit_factor", "expectancy_pct", "median_return_pct"]].to_dict("records")
    cost_rows = cost_target[["cost_label", "total_cost_bps", "trades", "win_rate", "profit_factor", "expectancy_pct", "median_return_pct"]].to_dict("records")
    annual_rows = annual_target[["year_label", "year", "filled_trades", "win_rate", "profit_factor", "expectancy_filled_pct", "median_return_pct"]].to_dict("records")
    decision_rows = decision[["check", "observed", "expected", "status_label"]].to_dict("records")

    manifest = {
        "version": 1,
        "surface": "report",
        "title": "Verdetto strategia small-cap momentum v1",
        "description": "Backtest storico Alpaca SIP della strategia continuation congelata.",
        "generatedAt": generated_at,
        "sources": sources,
        "cards": [
            {"id": "trades", "dataset": "headline", "sourceId": "primary_metrics", "description": "Trade target +20% nel periodo primario 2021–2025.", "metrics": [{"label": "Trade primari", "field": "trades", "format": "number"}]},
            {"id": "pf", "dataset": "headline", "sourceId": "primary_metrics", "description": "Profit factor netto a 100 bps; sotto 1 indica perdite lorde superiori ai profitti lordi.", "metrics": [{"label": "Profit factor", "field": "profit_factor", "format": "number"}]},
            {"id": "expectancy", "dataset": "headline", "sourceId": "primary_metrics", "description": "Rendimento medio netto per trade a 100 bps.", "metrics": [{"label": "Expectancy", "field": "expectancy", "format": "percent", "signed": True}]},
            {"id": "median", "dataset": "headline", "sourceId": "primary_metrics", "description": "Rendimento netto del trade mediano a 100 bps.", "metrics": [{"label": "Mediana", "field": "median_return", "format": "percent", "signed": True}]},
            {"id": "years", "dataset": "headline", "sourceId": "annual_metrics", "description": "Anni con expectancy positiva su cinque anni primari.", "metrics": [{"label": "Anni positivi su 5", "field": "positive_years", "format": "number"}]},
        ],
        "charts": [
            {
                "id": "exit_comparison", "title": "Expectancy per variante di uscita", "subtitle": "2021–2025, 83 trade per variante, costo round-trip 100 bps", "showDescription": True,
                "intent": "comparison", "question": "Una diversa uscita rende positiva la strategia?", "rationale": "Barre orizzontali per confrontare quattro categorie con valori firmati.",
                "type": "horizontalBar", "dataset": "exit_100", "sourceId": "primary_metrics", "layout": "full", "valueFormat": "percent", "unit": "%",
                "encodings": {"x": {"field": "variant_label", "type": "nominal", "label": "Uscita"}, "y": {"field": "expectancy_pct", "type": "quantitative", "format": "percent", "label": "Expectancy netta"}, "tooltip": [{"field": "profit_factor", "type": "quantitative", "label": "Profit factor"}, {"field": "median_return_pct", "type": "quantitative", "format": "percent", "label": "Mediana"}]},
                "referenceLines": [{"axis": "y", "value": 0, "label": "Pareggio", "color": "neutral"}], "settings": {"sort": "ascending", "showValues": True}, "palette": {"kind": "sequential", "name": "blue"}, "surface": {"surface": "card", "viewMode": "both"},
            },
            {
                "id": "cost_sensitivity", "title": "Expectancy target +20% per costo", "subtitle": "2021–2025; quattro scenari discreti di costo round-trip", "showDescription": True,
                "intent": "comparison", "question": "Quanto dipende il risultato dai costi?", "rationale": "Barre per quattro scenari discreti; una linea suggerirebbe una granularità non osservata.",
                "type": "bar", "dataset": "cost_target", "sourceId": "primary_metrics", "layout": "full", "valueFormat": "percent", "unit": "%",
                "encodings": {"x": {"field": "cost_label", "type": "ordinal", "label": "Costo round-trip"}, "y": {"field": "expectancy_pct", "type": "quantitative", "format": "percent", "label": "Expectancy netta"}, "tooltip": [{"field": "profit_factor", "type": "quantitative", "label": "Profit factor"}, {"field": "median_return_pct", "type": "quantitative", "format": "percent", "label": "Mediana"}]},
                "referenceLines": [{"axis": "y", "value": 0, "label": "Pareggio", "color": "neutral"}], "settings": {"sort": "custom", "showValues": True}, "palette": {"kind": "sequential", "name": "blue"}, "surface": {"surface": "card", "viewMode": "both"},
            },
            {
                "id": "annual_stability", "title": "Expectancy annuale target +20%", "subtitle": "2021–2025, costo round-trip 100 bps; numero di trade variabile per anno", "showDescription": True,
                "intent": "comparison", "question": "Il risultato è stabile tra gli anni?", "rationale": "Barre per cinque periodi discreti con campioni annuali piccoli.",
                "type": "bar", "dataset": "annual_target", "sourceId": "annual_metrics", "layout": "full", "valueFormat": "percent", "unit": "%",
                "encodings": {"x": {"field": "year_label", "type": "ordinal", "label": "Anno"}, "y": {"field": "expectancy_filled_pct", "type": "quantitative", "format": "percent", "label": "Expectancy netta"}, "tooltip": [{"field": "filled_trades", "type": "quantitative", "label": "Trade"}, {"field": "profit_factor", "type": "quantitative", "label": "Profit factor"}, {"field": "median_return_pct", "type": "quantitative", "format": "percent", "label": "Mediana"}]},
                "referenceLines": [{"axis": "y", "value": 0, "label": "Pareggio", "color": "neutral"}], "settings": {"sort": "custom", "showValues": True}, "palette": {"kind": "sequential", "name": "orange"}, "surface": {"surface": "card", "viewMode": "both"},
            },
        ],
        "tables": [
            {
                "id": "decision_table", "title": "Gate decisionali congelati", "subtitle": "Tutti i sei criteri di promozione della v1", "showDescription": True,
                "dataset": "decision_checks", "sourceId": "decision_checks", "layout": "full", "density": "spacious", "defaultSort": {"field": "check", "direction": "asc"},
                "columns": [{"field": "check", "label": "Gate", "type": "text"}, {"field": "observed", "label": "Osservato", "type": "text"}, {"field": "expected", "label": "Richiesto", "type": "text"}, {"field": "status_label", "label": "Esito", "type": "text"}],
            }
        ],
        "blocks": [
            {"id": "title", "type": "markdown", "body": "# Verdetto strategia small-cap momentum v1"},
            {"id": "summary", "type": "markdown", "body": "## La v1 non mostra un edge automatizzabile\n\n**Decisione: rifiutare questa implementazione.** Il backtest pluriennale non sostiene il collegamento a IBKR o MetaTrader, neppure in paper come presunta conferma della strategia. Il risultato vale per le regole meccaniche congelate; non dimostra che ogni possibile lettura discrezionale del pattern sia inefficace."},
            {"id": "headline_metrics", "type": "metric-strip", "cardIds": ["trades", "pf", "expectancy", "median", "years"]},
            {"id": "exits_text", "type": "markdown", "sourceId": "primary_metrics", "body": "## Cambiare l'uscita non recupera il segnale\n\nA 100 bps tutte e quattro le varianti hanno expectancy negativa. Il target +20% chiude con profit factor 0,741, expectancy -0,782% e mediana -2,392% su 83 trade. **Il problema è nel setup/trigger formalizzato, non soltanto nel target scelto.**"},
            {"id": "exits_chart", "type": "chart", "chartId": "exit_comparison", "layout": "full"},
            {"id": "cost_text", "type": "markdown", "sourceId": "primary_metrics", "body": "## I costi rendono fragile anche lo scenario più ottimistico\n\nCon il target +20%, già a 24 bps l'expectancy è -0,041% e il profit factor 0,984. All'aumentare dei costi il deterioramento è monotono. **Non esiste margine economico sufficiente per spread, slippage variabile, halt e impatto non modellati.**"},
            {"id": "cost_chart", "type": "chart", "chartId": "cost_sensitivity", "layout": "full"},
            {"id": "annual_text", "type": "markdown", "sourceId": "annual_metrics", "body": "## Quattro anni su cinque sono negativi\n\nSoltanto il 2023 ha expectancy positiva. Gli altri quattro anni sono negativi e le mediane annuali sono tutte sotto zero. I campioni annuali sono piccoli, ma la direzione non è compatibile con un edge stabile pronto per l'automazione."},
            {"id": "annual_chart", "type": "chart", "chartId": "annual_stability", "layout": "full"},
            {"id": "gates_text", "type": "markdown", "sourceId": "decision_checks", "body": "## Nessun gate di promozione passa\n\nFalliscono numerosità, profit factor, mediana, limite inferiore bootstrap, stabilità annuale e robustezza delle uscite. **Un risultato inconclusivo ma con stima centrale negativa non giustifica un test broker come strategia candidata.**"},
            {"id": "gates_table", "type": "table", "tableId": "decision_table", "layout": "full"},
            {"id": "scope", "type": "markdown", "sourceId": "quality", "body": "## Dati completi per il perimetro definito\n\nIl run usa barre reali 15 minuti Alpaca SIP: 301 finestre su 301 caricate, 373.857 barre e copertura del 100% delle 328 sessioni evento richieste. Non risultano timestamp duplicati né finestre fallite. Questo riduce il rischio di un errore di download, ma non elimina i bias dell'universo."},
            {"id": "definitions", "type": "markdown", "sourceId": "frozen_spec", "body": "## Cosa è stato misurato\n\nIl periodo decisionale è 2021–2025; il 2026 è tenuto come development. Un trade nasce da spike, consolidamento, resistenza ripetuta, breakout, primo pullback che tiene e ingresso alla barra successiva. Il costo principale è 100 bps round-trip. Profit factor sopra 1 indica profitti lordi maggiori delle perdite lorde; expectancy e mediana sono rendimenti netti per trade."},
            {"id": "method", "type": "markdown", "sourceId": "frozen_spec", "body": "## Metodo causale e riconciliato\n\nLo screening usa soltanto sessioni precedenti; livello, breakout, hold e ingresso rispettano l'ordine temporale. Il ledger stressato è stato ricalcolato indipendentemente e riconciliato esattamente con le tabelle aggregate. Le quattro uscite sono scenari alternativi sullo stesso segnale, non repliche indipendenti."},
            {"id": "uncertainty", "type": "markdown", "sourceId": "bootstrap", "body": f"## L'incertezza non permette una promozione\n\nPer target +20% a 100 bps, il bootstrap descrittivo al 95% va da {boot.ci_low_pct:.3%} a {boot.ci_high_pct:.3%}. Include zero: non è una prova definitiva che la vera expectancy sia negativa. Tuttavia la media osservata è negativa e tutti gli altri gate falliscono; l'evidenza disponibile non sostiene l'esistenza di edge."},
            {"id": "limits", "type": "markdown", "body": "## Limiti che potrebbero cambiare l'interpretazione\n\nL'universo usa componenti IWM correnti e quindi soffre di survivorship bias; mancano delisted point-in-time, quote bid/ask, halt/LULD e percorso tick intrabar. La strategia originale era discrezionale: la formalizzazione può non catturare selezione del contesto, qualità del catalyst o lettura del tape. Questi limiti impediscono affermazioni universali, ma non trasformano risultati negativi in evidenza positiva."},
            {"id": "next", "type": "markdown", "body": "## Prossimo passo consigliato\n\n1. Non collegare la v1 a IBKR o MetaTrader.\n2. Se esiste una nuova ipotesi concreta, definirla come v2 e congelarla prima di altri test.\n3. Separare ricerca e conferma: non scegliere parametri sul 2021–2025 e poi chiamare lo stesso periodo out-of-sample.\n4. Richiedere per la v2 un universo point-in-time, costi realistici e una finestra veramente non osservata prima di qualsiasi paper trading."},
            {"id": "questions", "type": "markdown", "body": "## Domande ancora aperte\n\n- Un filtro point-in-time su market cap, float, prezzo e catalyst elimina abbastanza falsi segnali?\n- La resistenza discrezionale può essere approssimata meglio senza introdurre lookahead?\n- Quote e halt reali rendono l'esecuzione peggiore rispetto allo stress deterministico?\n\nQueste sono ipotesi per una strategia nuova, non correzioni sufficienti a salvare retroattivamente la v1."},
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
                "exit_100": exit_rows,
                "cost_target": cost_rows,
                "annual_target": annual_rows,
                "decision_checks": decision_rows,
            },
        },
        "sources": sources,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "artifact.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUTPUT / "artifact.json")


if __name__ == "__main__":
    main()
