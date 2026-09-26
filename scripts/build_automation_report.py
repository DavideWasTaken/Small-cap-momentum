from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "automation_report"
GENERATED_AT = "2026-07-11T00:00:00Z"


def records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def cost_sensitivity(path: Path, mode: str) -> pd.DataFrame:
    trades = pd.read_csv(path / "trades.csv")
    trades = trades[trades["variant"] == "target_20"]
    rows = []
    for bps in [10, 25, 50, 100, 200]:
        slip = bps / 10_000
        returns = []
        for _, trade in trades.iterrows():
            entry = trade.entry_price_raw * (1 + slip)
            exit_raw = (
                entry * 1.20
                if str(trade.exit_reason).startswith("target")
                else trade.exit_price_raw
            )
            exit_price = exit_raw * (1 - slip)
            commission = 0.0002 * (entry + exit_price)
            returns.append((exit_price - entry - commission) / entry)
        rows.append(
            {
                "mode": mode,
                "slippage_bps_side": bps,
                "bps_label": f"{bps} bps",
                "expectancy_pct": float(np.mean(returns)),
                "trades": len(returns),
            }
        )
    return pd.DataFrame(rows)


def source(source_id: str, label: str, path: str, sql: str, tables: list[str]) -> dict:
    return {
        "id": source_id,
        "label": label,
        "path": path,
        "query": {
            "engine": "duckdb",
            "language": "sql",
            "executed_at": GENERATED_AT,
            "description": label,
            "sql": sql,
            "tables_used": tables,
        },
    }


def main() -> None:
    extended_path = ROOT / "outputs" / "iwm_automated_v2"
    regular_path = ROOT / "outputs" / "iwm_regular_only"
    base_path = ROOT / "outputs" / "iwm_automated"
    holdings = pd.read_csv(base_path / "iwm_holdings_current.csv")
    daily = pd.read_csv(base_path / "daily_history.csv")
    movers = pd.read_csv(base_path / "daily_mover_events.csv")
    extended_signals = pd.read_csv(extended_path / "signals.csv")
    regular_signals = pd.read_csv(regular_path / "signals.csv")
    extended_metrics = pd.read_csv(extended_path / "metrics.csv").assign(mode="Extended")
    regular_metrics = pd.read_csv(regular_path / "metrics.csv").assign(mode="Regular-only")
    mode_metrics = pd.concat([extended_metrics, regular_metrics], ignore_index=True)
    extended_target = pd.read_csv(extended_path / "trades.csv")
    extended_target = extended_target[extended_target.variant == "target_20"].copy()
    extended_target["outcome"] = np.where(extended_target.return_pct > 0, "Positive", "Negative")
    extended_target = extended_target.sort_values("return_pct")
    audit = pd.read_csv(extended_path / "candidate_audit.csv")
    costs = pd.concat(
        [cost_sensitivity(extended_path, "Extended"), cost_sensitivity(regular_path, "Regular-only")],
        ignore_index=True,
    )
    extended_keys = set(zip(extended_signals.ticker, extended_signals.trigger_session))
    regular_keys = set(zip(regular_signals.ticker, regular_signals.trigger_session))
    overlap = len(extended_keys & regular_keys)
    union = len(extended_keys | regular_keys)
    summary = {
        "iwm_holdings": len(holdings),
        "daily_tickers": int(daily.Ticker.nunique()),
        "daily_spike_events": len(movers),
        "intraday_candidates": 22,
        "extended_signals": len(extended_signals),
        "regular_signals": len(regular_signals),
        "exact_overlap": overlap,
        "overlap_jaccard": overlap / union,
    }

    summary_sql = """WITH
h AS (SELECT * FROM read_csv_auto('outputs/iwm_automated/iwm_holdings_current.csv')),
d AS (SELECT * FROM read_csv_auto('outputs/iwm_automated/daily_history.csv')),
m AS (SELECT * FROM read_csv_auto('outputs/iwm_automated/daily_mover_events.csv')),
e AS (SELECT * FROM read_csv_auto('outputs/iwm_automated_v2/signals.csv')),
r AS (SELECT * FROM read_csv_auto('outputs/iwm_regular_only/signals.csv')),
both AS (SELECT ticker || '|' || trigger_session AS k FROM e UNION ALL SELECT ticker || '|' || trigger_session FROM r)
SELECT (SELECT COUNT(*) FROM h) AS iwm_holdings, (SELECT COUNT(DISTINCT Ticker) FROM d) AS daily_tickers,
(SELECT COUNT(*) FROM m) AS daily_spike_events, 22 AS intraday_candidates,
(SELECT COUNT(*) FROM e) AS extended_signals, (SELECT COUNT(*) FROM r) AS regular_signals,
(SELECT COUNT(*) FROM e JOIN r USING (ticker, trigger_session)) AS exact_overlap,
(SELECT COUNT(*) FROM e JOIN r USING (ticker, trigger_session))::DOUBLE / (SELECT COUNT(DISTINCT k) FROM both) AS overlap_jaccard"""
    metrics_sql = """SELECT 'Extended' AS mode, * FROM read_csv_auto('outputs/iwm_automated_v2/metrics.csv')
UNION ALL SELECT 'Regular-only' AS mode, * FROM read_csv_auto('outputs/iwm_regular_only/metrics.csv')"""
    trades_sql = """SELECT *, CASE WHEN return_pct > 0 THEN 'Positive' ELSE 'Negative' END AS outcome
FROM read_csv_auto('outputs/iwm_automated_v2/trades.csv') WHERE variant = 'target_20' ORDER BY return_pct"""
    audit_sql = "SELECT * FROM read_csv_auto('outputs/iwm_automated_v2/candidate_audit.csv')"
    costs_sql = """WITH cost(bps) AS (VALUES (10), (25), (50), (100), (200)),
trades AS (
  SELECT 'Extended' AS mode, * FROM read_csv_auto('outputs/iwm_automated_v2/trades.csv') WHERE variant='target_20'
  UNION ALL SELECT 'Regular-only' AS mode, * FROM read_csv_auto('outputs/iwm_regular_only/trades.csv') WHERE variant='target_20'
), calc AS (
  SELECT mode, bps, entry_price_raw*(1+bps/10000.0) AS entry,
  CASE WHEN starts_with(exit_reason,'target') THEN entry_price_raw*(1+bps/10000.0)*1.20 ELSE exit_price_raw END AS raw_exit
  FROM trades CROSS JOIN cost
)
SELECT mode, bps AS slippage_bps_side, CAST(bps AS VARCHAR)||' bps' AS bps_label,
AVG((raw_exit*(1-bps/10000.0)-entry-0.0002*(entry+raw_exit*(1-bps/10000.0)))/entry) AS expectancy_pct,
COUNT(*) AS trades FROM calc GROUP BY mode,bps ORDER BY bps,mode"""

    sources = [
        source("summary", "Copertura e sovrapposizione dei segnali", "outputs", summary_sql, [
            "outputs/iwm_automated/iwm_holdings_current.csv",
            "outputs/iwm_automated/daily_history.csv",
            "outputs/iwm_automated/daily_mover_events.csv",
            "outputs/iwm_automated_v2/signals.csv",
            "outputs/iwm_regular_only/signals.csv",
        ]),
        source("metrics", "Metriche per modalità e uscita", "outputs", metrics_sql, [
            "outputs/iwm_automated_v2/metrics.csv", "outputs/iwm_regular_only/metrics.csv"
        ]),
        source("trades", "Esiti target 20% della modalità extended", "outputs/iwm_automated_v2/trades.csv", trades_sql, [
            "outputs/iwm_automated_v2/trades.csv"
        ]),
        source("audit", "Audit dei candidati intraday", "outputs/iwm_automated_v2/candidate_audit.csv", audit_sql, [
            "outputs/iwm_automated_v2/candidate_audit.csv"
        ]),
        source("costs", "Sensibilità dell'expectancy allo slippage", "outputs", costs_sql, [
            "outputs/iwm_automated_v2/trades.csv", "outputs/iwm_regular_only/trades.csv"
        ]),
        {"id": "code", "label": "Pipeline Python", "path": "src/smallcap_bt"},
        {"id": "assumptions", "label": "Assunzioni documentate", "path": "ASSUNZIONI.md"},
    ]

    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": "Automazione del setup small-cap momentum",
            "description": "Screening IWM, backtest 15m e sensibilità extended versus regular-only.",
            "generatedAt": GENERATED_AT,
            "sources": sources,
            "cards": [
                {"id": "c_universe", "description": "Azioni USA valide estratte dall'export IWM corrente.", "dataset": "summary", "sourceId": "summary", "metrics": [{"label": "Universo IWM", "field": "iwm_holdings", "format": "number"}]},
                {"id": "c_movers", "description": "Eventi daily che superano tutti i filtri fissi.", "dataset": "summary", "sourceId": "summary", "metrics": [{"label": "Spike qualificati", "field": "daily_spike_events", "format": "number"}]},
                {"id": "c_signals", "description": "Segnali dopo il limite anti-inseguimento del 20%.", "dataset": "summary", "sourceId": "summary", "metrics": [{"label": "Segnali extended", "field": "extended_signals", "format": "number"}]},
                {"id": "c_overlap", "description": "Jaccard su ticker e sessione di trigger tra le due definizioni.", "dataset": "summary", "sourceId": "summary", "metrics": [{"label": "Overlap esatto", "field": "overlap_jaccard", "format": "percent"}]},
            ],
            "charts": [
                {
                    "id": "ch_expectancy", "title": "Expectancy per uscita e definizione del setup",
                    "subtitle": "Rendimento medio netto per trade, 14 segnali extended e 15 regular-only.",
                    "type": "bar", "dataset": "mode_metrics", "sourceId": "metrics", "layout": "full", "maxRows": 20,
                    "encodings": {
                        "x": {"field": "variant", "type": "nominal", "label": "Uscita"},
                        "y": {"field": "expectancy_pct", "type": "quantitative", "format": "percent", "label": "Expectancy"},
                        "color": {"field": "mode", "type": "nominal", "label": "Setup"},
                        "tooltip": [
                            {"field": "trades", "type": "quantitative", "label": "Trade"},
                            {"field": "win_rate", "type": "quantitative", "format": "percent", "label": "Win rate"},
                            {"field": "profit_factor", "type": "quantitative", "label": "Profit factor"},
                            {"field": "max_drawdown_pct", "type": "quantitative", "format": "percent", "label": "Max drawdown"}
                        ]
                    }, "valueFormat": "percent"
                },
                {
                    "id": "ch_costs", "title": "Expectancy target 20% per ipotesi di slippage",
                    "subtitle": "Costi per lato da 10 a 200 bps; commissione fissa 2 bps per lato.",
                    "type": "bar", "dataset": "cost_rows", "sourceId": "costs", "layout": "full", "maxRows": 20,
                    "encodings": {
                        "x": {"field": "bps_label", "type": "ordinal", "label": "Slippage per lato"},
                        "y": {"field": "expectancy_pct", "type": "quantitative", "format": "percent", "label": "Expectancy"},
                        "color": {"field": "mode", "type": "nominal", "label": "Setup"},
                        "tooltip": [{"field": "trades", "type": "quantitative", "label": "Trade"}]
                    }, "valueFormat": "percent"
                },
            ],
            "tables": [
                {
                    "id": "tb_metrics", "title": "Metriche comparative", "subtitle": "Stesso universo, costi e sizing; cambia solo l'uso delle barre extended nel setup.",
                    "dataset": "mode_metrics", "sourceId": "metrics", "defaultSort": {"field": "variant", "direction": "asc"}, "density": "spacious", "layout": "full",
                    "columns": [
                        {"field": "mode", "label": "Setup", "type": "text"}, {"field": "variant", "label": "Uscita", "type": "text"},
                        {"field": "trades", "label": "Trade", "format": "number"}, {"field": "win_rate", "label": "Win rate", "format": "percent"},
                        {"field": "profit_factor", "label": "PF", "format": "number"}, {"field": "expectancy_pct", "label": "Expectancy", "format": "percent", "movement": True},
                        {"field": "median_return_pct", "label": "Mediana", "format": "percent", "movement": True},
                        {"field": "max_drawdown_pct", "label": "Max DD", "format": "percent", "movement": True},
                        {"field": "total_return_pct", "label": "Equity return", "format": "percent", "movement": True}
                    ]
                },
                {
                    "id": "tb_trades", "title": "Esiti individuali — target 20%, extended", "subtitle": "Una riga per ticker; ordinamento dal rendimento peggiore al migliore.",
                    "dataset": "target_rows", "sourceId": "trades", "defaultSort": {"field": "return_pct", "direction": "asc"}, "density": "dense", "layout": "full",
                    "columns": [
                        {"field": "ticker", "label": "Ticker", "type": "text"}, {"field": "trigger_session", "label": "Trigger", "type": "date"},
                        {"field": "entry_price_raw", "label": "Entry ($)", "format": "number"}, {"field": "resistance_level", "label": "Livello ($)", "format": "number"},
                        {"field": "return_pct", "label": "Return", "format": "percent", "movement": True}, {"field": "r_multiple", "label": "R", "format": "number", "movement": True},
                        {"field": "exit_reason", "label": "Uscita", "type": "text"}, {"field": "mfe_pct", "label": "MFE", "format": "percent"}
                    ]
                },
                {
                    "id": "tb_audit", "title": "Audit dei 22 candidati intraday", "subtitle": "Stadio massimo raggiunto dalla modalità extended v2, con limite anti-inseguimento.",
                    "dataset": "audit_rows", "sourceId": "audit", "defaultSort": {"field": "status", "direction": "asc"}, "density": "dense", "layout": "full",
                    "columns": [
                        {"field": "ticker", "label": "Ticker", "type": "text"}, {"field": "status", "label": "Esito pipeline", "type": "text"},
                        {"field": "intraday_spike_count", "label": "Spike 15m", "format": "number"}, {"field": "valid_setup_session_count", "label": "Sessioni setup", "format": "number"},
                        {"field": "signal_count", "label": "Segnali", "format": "number"}, {"field": "signal_sessions", "label": "Sessione segnale", "type": "text"}
                    ]
                }
            ],
            "blocks": [
                {"id": "title", "type": "markdown", "body": "# Automazione del setup small-cap momentum"},
                {"id": "summary_text", "type": "markdown", "body": "## Sintesi tecnica\n\n**La procedura è automatizzabile end-to-end, ma il livello di resistenza non è ancora definito in modo stabile.** Il sistema importa l'universo IWM, esegue il daily scan, riduce circa 1.900 titoli a 22 candidati, scarica i 15 minuti e genera segnali, stop, uscite, metriche e grafici senza override. Dopo il controllo visivo è stato aggiunto un limite anti-inseguimento: nessuna entry oltre il 20% sopra la resistenza.\n\nLa modalità extended produce 14 segnali e risultati descrittivi forti; la regular-only ne produce 15 ma con performance molto più debole. Solo 6 coppie ticker/data coincidono esattamente. Quindi l'orchestrazione è pronta, mentre la definizione quantitativa del livello richiede dati extended affidabili o una regola più robusta."},
                {"id": "cards", "type": "metric-strip", "cardIds": ["c_universe", "c_movers", "c_signals", "c_overlap"]},
                {"id": "coverage", "type": "markdown", "body": "## Lo screening elimina quasi tutto l'universo senza selezione manuale\n\nL'export IWM corrente fornisce 1.937 azioni USA valide; Yahoo restituisce daily per 1.926. Le soglie fisse trovano 22 eventi spike e tutti i 22 candidati hanno dati 15m. L'audit distingue automaticamente chi non forma un consolidamento valido da chi forma il setup ma non completa breakout, hold ed entry."},
                {"id": "performance_intro", "type": "markdown", "body": "## Il segnale economico è positivo, ma dipende dalla sessione usata per il livello\n\nNella modalità extended l'uscita target 20% mostra expectancy +4,27%, win rate 57,1% e profit factor 5,46 su 14 trade. Nella regular-only l'expectancy scende a +1,12%, il win rate a 46,7% e il profit factor a 1,51 su 15 trade. Il grafico confronta tutte le uscite; la distanza tra le serie è una misura di fragilità metodologica, non un vantaggio da ottimizzare."},
                {"id": "expectancy", "type": "chart", "chartId": "ch_expectancy"},
                {"id": "metrics", "type": "table", "tableId": "tb_metrics"},
                {"id": "cost_intro", "type": "markdown", "body": "## I costi separano la versione robusta da quella marginale\n\nCon target 20%, l'extended resta positiva nello stress fino a 200 bps per lato, sostenuta soprattutto da CLRO e RXT. La regular-only passa da +1,12% a 10 bps a -0,61% con 100 bps e -2,50% con 200 bps. Il test è conservativo sui costi proporzionali, ma non simula halt, fill parziali o spread dinamico."},
                {"id": "cost_chart", "type": "chart", "chartId": "ch_costs"},
                {"id": "outcomes_intro", "type": "markdown", "body": "## I risultati non dipendono soltanto da CLRO, ma restano concentrati\n\nNella modalità extended, CLRO e RXT raggiungono il target 20%; BAND, EVC, TRAX e FBRX contribuiscono con guadagni inferiori. I tre migliori trade rappresentano circa il 68% della somma dei rendimenti positivi. La tabella permette di verificare vincitori, perdenti, MFE ed esecuzione di ogni segnale."},
                {"id": "outcomes", "type": "table", "tableId": "tb_trades"},
                {"id": "audit_intro", "type": "markdown", "body": "## I rifiuti sono tracciabili e quindi operativamente automatizzabili\n\nOtto candidati non generano un segnale extended v2: ELTX non costruisce un consolidamento/resistenza valido; BFLY, BLZE, EVER, INOD, OPTU, TNGX e UMAC costruiscono almeno un setup ma non completano una sequenza breakout–hold–entry eseguibile. INOD viene escluso dal nuovo limite anti-inseguimento del 20%. L'audit evita che i casi esclusi spariscano silenziosamente."},
                {"id": "audit", "type": "table", "tableId": "tb_audit"},
                {"id": "definitions", "type": "markdown", "body": "## Perimetro e definizioni\n\n**Universo:** partecipazioni correnti IWM, quindi non point-in-time. **Daily screen:** rendimento aggiustato almeno +50%, volume almeno 5× la media precedente, prezzo precedente 0,50–50 dollari e almeno 1 milione di dollari scambiati nel giorno dello spike. **Setup:** 1–5 sessioni successive, range e cluster di almeno tre massimi locali. **Trigger:** breakout, primo pullback, due barre di hold e ingresso alla barra successiva, non oltre +20% dal livello. **Costi base:** 10 bps di slippage e 2 bps di commissione per lato."},
                {"id": "method", "type": "markdown", "body": "## Metodo e controlli\n\nIl daily scan usa prezzi aggiustati per evitare falsi spike da split; livelli ed esecuzioni usano prezzi raw 15m. Ogni setup usa solo date precedenti alla sessione candidata; l'ordine entra sulla barra successiva. Stop e target nella stessa barra sono risolti pessimisticamente. Sono stati ispezionati graficamente CLRO, FBRX, INOD e RXT; INOD ha rivelato il difetto di inseguimento poi corretto. Sei test automatici coprono parsing universo, daily screen, resistenza, lookahead, ambiguità intrabar e trailing."},
                {"id": "limits", "type": "markdown", "body": "## Limiti e robustezza\n\n**Definizione instabile:** overlap esatto 26,1% tra extended e regular-only. **Dati:** Yahoo assegna volume zero quasi ovunque fuori orario; i livelli extended possono essere validi come prezzo ma non come prova di liquidità. **Bias:** IWM è corrente e i parametri sono stati formalizzati osservando CLRO. **Incertezza:** 14–15 trade restano pochi; il bootstrap descrittivo della media target 20% è circa +0,5%–+8,5% per extended e -2,4%–+5,1% per regular-only. Non sono intervalli out-of-sample. **Esecuzione:** mancano spread, halt e market impact."},
                {"id": "next", "type": "markdown", "body": "## Prossimi passi raccomandati\n\n1. Usare Alpaca SIP o Polygon per volume e prezzi extended affidabili.\n2. Congelare due specifiche candidate: regular-only e extended con volume reale.\n3. Eseguire almeno 3–5 anni su universo point-in-time, senza aggiustare le soglie sul test.\n4. Aggiungere quote/spread, halt e capacità massima per trade.\n5. Accettare l'automazione economica solo se i risultati restano positivi out-of-sample e tra anni, settori e regimi."},
                {"id": "questions", "type": "markdown", "body": "## Domande aperte\n\nLa resistenza deve usare massimi locali, chiusure o volume-at-price? Il pullback può chiudere temporaneamente sotto il livello oppure deve riconquistarlo in una sola barra? Quale feed extended rappresenta davvero i fill disponibili? Queste scelte cambiano materialmente i segnali e devono essere preregistrate prima del backtest pluriennale."}
            ]
        },
        "snapshot": {
            "version": 1, "generatedAt": GENERATED_AT, "status": "ready",
            "datasets": {
                "summary": [summary], "mode_metrics": records(mode_metrics),
                "target_rows": records(extended_target), "audit_rows": records(audit), "cost_rows": records(costs)
            }
        },
        "sources": sources,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "artifact.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
