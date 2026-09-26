from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "outputs" / "automation_readiness"
OUT = ROOT / "outputs" / "readiness_report"
GENERATED_AT = "2026-07-11T00:00:00Z"


def records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def csv_source(source_id: str, label: str, filename: str, sql: str) -> dict:
    path = f"outputs/automation_readiness/{filename}"
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
            "tables_used": [path],
        },
    }


def main() -> None:
    stress = pd.read_csv(DATA / "execution_stress.csv")
    sensitivity = pd.read_csv(DATA / "parameter_sensitivity.csv")
    liquidity = pd.read_csv(DATA / "liquidity_diagnostics.csv")
    split = pd.read_csv(DATA / "chronological_split.csv")
    overlap = pd.read_csv(DATA / "signal_overlap.csv")
    bootstrap = pd.read_csv(DATA / "bootstrap_summary.csv")
    scorecard = pd.read_csv(DATA / "readiness_scorecard.csv")

    stress_zero_delay = stress[stress.delay_bars == 0].copy()
    stress_zero_delay["cost_label"] = stress_zero_delay.total_cost_bps.map(
        lambda value: f"{int(value)} bps"
    )
    sensitivity = sensitivity.sort_values("median_return_pct")
    liquidity = liquidity.sort_values("participation_of_15m_volume", ascending=False)
    production = stress_zero_delay[stress_zero_delay.total_cost_bps == 100].iloc[0]
    late = split[split.period == "late_half"].iloc[0]
    production_bootstrap = bootstrap[bootstrap.scenario == "production_100bps"].iloc[0]
    summary = {
        "observed_trades": int(production.eligible_signals),
        "profit_factor_100bps": float(production.profit_factor),
        "median_return_100bps": float(production.median_return_pct),
        "expectancy_100bps": float(production.expectancy_filled_pct),
        "late_half_expectancy": float(late.expectancy_filled_pct),
        "bootstrap_low_100bps": float(production_bootstrap.ci_low_pct),
        "blocking_failures": int((scorecard.status == "FAIL").sum()),
        "liquid_signal_share": float(
            (liquidity.participation_of_15m_volume <= 0.01).mean()
        ),
        "parameter_robust_share": float(
            ((sensitivity.profit_factor >= 1.30) & (sensitivity.median_return_pct > 0)).mean()
        ),
        "signal_overlap": float(overlap.iloc[0].jaccard),
    }

    sources = [
        csv_source(
            "stress",
            "Stress di costi e ritardo d'esecuzione",
            "execution_stress.csv",
            "SELECT * FROM read_csv_auto('outputs/automation_readiness/execution_stress.csv') ORDER BY total_cost_bps, delay_bars",
        ),
        csv_source(
            "sensitivity",
            "Sensibilità one-at-a-time dei parametri",
            "parameter_sensitivity.csv",
            "SELECT * FROM read_csv_auto('outputs/automation_readiness/parameter_sensitivity.csv') ORDER BY median_return_pct",
        ),
        csv_source(
            "liquidity",
            "Diagnostica di liquidità alla barra d'ingresso",
            "liquidity_diagnostics.csv",
            "SELECT * FROM read_csv_auto('outputs/automation_readiness/liquidity_diagnostics.csv') ORDER BY participation_of_15m_volume DESC",
        ),
        csv_source(
            "split",
            "Split cronologico del campione regular-only",
            "chronological_split.csv",
            "SELECT * FROM read_csv_auto('outputs/automation_readiness/chronological_split.csv')",
        ),
        csv_source(
            "bootstrap",
            "Bootstrap descrittivo della media",
            "bootstrap_summary.csv",
            "SELECT * FROM read_csv_auto('outputs/automation_readiness/bootstrap_summary.csv')",
        ),
        csv_source(
            "scorecard",
            "Gate per la promozione al live",
            "readiness_scorecard.csv",
            "SELECT * FROM read_csv_auto('outputs/automation_readiness/readiness_scorecard.csv')",
        ),
        {
            "id": "ibkr",
            "label": "Documentazione ufficiale IBKR TWS API",
            "url": "https://ibkrcampus.com/campus/ibkr-api-page/twsapi-doc/",
        },
        {
            "id": "ibkr_orders",
            "label": "Documentazione ufficiale IBKR order types e bracket",
            "url": "https://ibkrcampus.com/campus/ibkr-api-page/order-types/",
        },
        {
            "id": "ibkr_paper",
            "label": "Limitazioni ufficiali IBKR paper trading",
            "url": "https://www.interactivebrokers.com/campus/glossary-terms/paper-trading-account/",
        },
        {
            "id": "mt5",
            "label": "Documentazione ufficiale MetaTrader 5 Python",
            "url": "https://www.mql5.com/en/docs/python_metatrader5",
        },
        {"id": "notebook", "label": "Notebook eseguito", "path": "notebooks/automation_readiness.ipynb"},
        {"id": "deployment", "label": "Piano di deployment", "path": "BROKER_DEPLOYMENT.md"},
    ]

    summary_source = {
        "id": "summary",
        "label": "Sintesi dei test di readiness",
        "path": "outputs/automation_readiness",
        "query": {
            "engine": "duckdb",
            "language": "sql",
            "executed_at": GENERATED_AT,
            "description": "Selezione dei gate e delle metriche decisive dai CSV di readiness.",
            "sql": """WITH s AS (SELECT * FROM read_csv_auto('outputs/automation_readiness/execution_stress.csv') WHERE total_cost_bps=100 AND delay_bars=0),
g AS (SELECT COUNT(*) FILTER (WHERE status='FAIL') AS blocking_failures FROM read_csv_auto('outputs/automation_readiness/readiness_scorecard.csv')),
t AS (SELECT expectancy_filled_pct AS late_half_expectancy FROM read_csv_auto('outputs/automation_readiness/chronological_split.csv') WHERE period='late_half'),
b AS (SELECT ci_low_pct AS bootstrap_low_100bps FROM read_csv_auto('outputs/automation_readiness/bootstrap_summary.csv') WHERE scenario='production_100bps'),
l AS (SELECT AVG((participation_of_15m_volume <= 0.01)::INT) AS liquid_signal_share FROM read_csv_auto('outputs/automation_readiness/liquidity_diagnostics.csv')),
p AS (SELECT AVG(((profit_factor >= 1.30) AND (median_return_pct > 0))::INT) AS parameter_robust_share FROM read_csv_auto('outputs/automation_readiness/parameter_sensitivity.csv')),
o AS (SELECT jaccard AS signal_overlap FROM read_csv_auto('outputs/automation_readiness/signal_overlap.csv'))
SELECT s.eligible_signals AS observed_trades, s.profit_factor AS profit_factor_100bps,
s.median_return_pct AS median_return_100bps, s.expectancy_filled_pct AS expectancy_100bps,
t.late_half_expectancy, b.bootstrap_low_100bps, g.blocking_failures, l.liquid_signal_share,
p.parameter_robust_share, o.signal_overlap FROM s CROSS JOIN g CROSS JOIN t CROSS JOIN b CROSS JOIN l CROSS JOIN p CROSS JOIN o""",
            "tables_used": [
                "outputs/automation_readiness/execution_stress.csv",
                "outputs/automation_readiness/readiness_scorecard.csv",
                "outputs/automation_readiness/chronological_split.csv",
                "outputs/automation_readiness/bootstrap_summary.csv",
            ],
        },
    }
    sources.insert(0, summary_source)

    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": "Readiness per trading automatico",
            "description": "Stress test del setup small-cap per IBKR e MetaTrader 5.",
            "generatedAt": GENERATED_AT,
            "sources": sources,
            "cards": [
                {
                    "id": "c_trades",
                    "description": "Trade regular-only disponibili, non out-of-sample.",
                    "dataset": "summary",
                    "sourceId": "summary",
                    "metrics": [{"label": "Trade osservati", "field": "observed_trades", "format": "number"}],
                },
                {
                    "id": "c_pf",
                    "description": "Target 20%, 100 bps round-trip, nessun ritardo aggiuntivo.",
                    "dataset": "summary",
                    "sourceId": "summary",
                    "metrics": [{"label": "PF a 100 bps", "field": "profit_factor_100bps", "format": "number"}],
                },
                {
                    "id": "c_median",
                    "description": "Rendimento mediano dopo 100 bps di costo complessivo.",
                    "dataset": "summary",
                    "sourceId": "summary",
                    "metrics": [{"label": "Mediana a 100 bps", "field": "median_return_100bps", "format": "percent", "signed": True}],
                },
                {
                    "id": "c_fail",
                    "description": "Criteri bloccanti non superati per il passaggio al live.",
                    "dataset": "summary",
                    "sourceId": "summary",
                    "metrics": [{"label": "Gate live falliti", "field": "blocking_failures", "format": "number"}],
                },
            ],
            "charts": [
                {
                    "id": "ch_cost",
                    "title": "Expectancy per costo round-trip",
                    "subtitle": "Target 20%, 15 segnali regular-only, nessun ritardo aggiuntivo.",
                    "type": "bar",
                    "dataset": "stress_zero_delay",
                    "sourceId": "stress",
                    "layout": "full",
                    "maxRows": 10,
                    "encodings": {
                        "x": {"field": "cost_label", "type": "ordinal", "label": "Costo complessivo"},
                        "y": {"field": "expectancy_filled_pct", "type": "quantitative", "format": "percent", "label": "Expectancy"},
                        "tooltip": [
                            {"field": "profit_factor", "type": "quantitative", "label": "Profit factor"},
                            {"field": "median_return_pct", "type": "quantitative", "format": "percent", "label": "Mediana"},
                            {"field": "win_rate", "type": "quantitative", "format": "percent", "label": "Win rate"},
                        ],
                    },
                    "valueFormat": "percent",
                },
                {
                    "id": "ch_params",
                    "title": "Mediana per scenario parametrico",
                    "subtitle": "Variazione di un solo parametro rispetto alla configurazione base regular-only.",
                    "type": "bar",
                    "dataset": "sensitivity",
                    "sourceId": "sensitivity",
                    "layout": "full",
                    "maxRows": 12,
                    "encodings": {
                        "x": {"field": "scenario", "type": "nominal", "label": "Scenario"},
                        "y": {"field": "median_return_pct", "type": "quantitative", "format": "percent", "label": "Mediana"},
                        "tooltip": [
                            {"field": "filled_trades", "type": "quantitative", "label": "Trade"},
                            {"field": "profit_factor", "type": "quantitative", "label": "Profit factor"},
                            {"field": "expectancy_filled_pct", "type": "quantitative", "format": "percent", "label": "Expectancy"},
                        ],
                    },
                    "valueFormat": "percent",
                },
            ],
            "tables": [
                {
                    "id": "tb_scorecard",
                    "title": "Gate di promozione al live",
                    "subtitle": "Soglie preregistrate per evitare una promozione basata sul solo profitto storico.",
                    "dataset": "scorecard",
                    "sourceId": "scorecard",
                    "defaultSort": {"field": "status", "direction": "asc"},
                    "density": "spacious",
                    "layout": "full",
                    "columns": [
                        {"field": "criterion", "label": "Criterio", "type": "text"},
                        {"field": "observed", "label": "Osservato", "format": "number"},
                        {"field": "operator", "label": "Test", "type": "text"},
                        {"field": "threshold", "label": "Soglia", "format": "number"},
                        {"field": "status", "label": "Esito", "type": "text"},
                    ],
                },
                {
                    "id": "tb_liquidity",
                    "title": "Capacità alla barra d'ingresso",
                    "subtitle": "Sizing su 100.000 USD; partecipazione calcolata sul volume aggregato della barra 15m.",
                    "dataset": "liquidity",
                    "sourceId": "liquidity",
                    "defaultSort": {"field": "participation_of_15m_volume", "direction": "desc"},
                    "density": "dense",
                    "layout": "full",
                    "columns": [
                        {"field": "ticker", "label": "Ticker", "type": "text"},
                        {"field": "shares_at_100k", "label": "Azioni", "format": "number"},
                        {"field": "position_notional", "label": "Notional $", "format": "currency"},
                        {"field": "entry_bar_dollar_volume", "label": "$ volume 15m", "format": "currency"},
                        {"field": "participation_of_15m_volume", "label": "Partecipazione", "format": "percent"},
                        {"field": "entry_bar_range_pct", "label": "Range barra", "format": "percent"},
                    ],
                },
            ],
            "blocks": [
                {"id": "title", "type": "markdown", "body": "# Readiness per trading automatico"},
                {
                    "id": "summary_text",
                    "type": "markdown",
                    "body": "## Sintesi tecnica\n\n**Il motore può essere collegato a un broker in modalità shadow/paper, ma non deve ancora trasmettere ordini live.** Con 100 bps di costo complessivo il profit factor scende a 1,15, la mediana è −1,10% e il limite inferiore bootstrap della media è −3,12%. Tutti gli 11 gate bloccanti per il live falliscono.\n\n**Piattaforma consigliata:** IBKR TWS API / IB Gateway, perché è più adatta alle azioni USA e supporta dati, callback d'ordine e bracket order. MetaTrader 5 resta condizionale al broker: simboli, azioni reali, routing e sessioni extended non sono garantiti dalla piattaforma stessa.",
                },
                {"id": "cards", "type": "metric-strip", "cardIds": ["c_trades", "c_pf", "c_median", "c_fail"]},
                {
                    "id": "cost_intro",
                    "type": "markdown",
                    "body": "## A 100 bps il margine economico è troppo sottile\n\nL'expectancy resta leggermente positiva (+0,39%), ma il profit factor 1,15 è sotto la soglia 1,30 e il trade mediano perde 1,10%. A 200 bps l'expectancy diventa −0,57% e il profit factor 0,82. Il grafico isola i costi senza ritardo extra; i ritardi di una o due barre non peggiorano questo piccolo campione, un risultato instabile che non va interpretato come beneficio della latenza.",
                },
                {"id": "cost_chart", "type": "chart", "chartId": "ch_cost"},
                {
                    "id": "time_intro",
                    "type": "markdown",
                    "body": "## La metà recente del campione è negativa\n\nI primi 7 trade hanno expectancy +4,43% e profit factor 5,30; gli ultimi 8 hanno expectancy −1,77%, mediana −2,42% e profit factor 0,45. Non è una prova di decadimento, ma impedisce di considerare stabile il risultato aggregato.",
                    "sourceId": "split",
                },
                {
                    "id": "param_intro",
                    "type": "markdown",
                    "body": "## Solo 2 scenari su 9 superano insieme PF e mediana\n\nTutti gli scenari one-at-a-time conservano una media positiva, ma soltanto il 22,2% raggiunge contemporaneamente profit factor almeno 1,30 e mediana positiva. La configurazione base ha mediana negativa; il risultato dipende ancora dai grandi vincitori.",
                    "sourceId": "sensitivity",
                },
                {"id": "param_chart", "type": "chart", "chartId": "ch_params"},
                {
                    "id": "liq_intro",
                    "type": "markdown",
                    "body": "## Il sizing è credibile solo per il 60% dei segnali\n\nCon il conto di riferimento da 100.000 USD, soltanto 9 segnali su 15 restano sotto l'1% del volume della barra d'ingresso. NMRA richiederebbe circa il 32,3% del volume 15m: il backtest non può assumere un fill con slippage fisso. Il filtro di partecipazione deve entrare nel motore prima del paper test.",
                    "sourceId": "liquidity",
                },
                {"id": "liq_table", "type": "table", "tableId": "tb_liquidity"},
                {
                    "id": "gate_intro",
                    "type": "markdown",
                    "body": "## Nessun gate live è superato nel suo insieme\n\nMancano campione out-of-sample, storia point-in-time, shadow fills e robustezza rispetto a costi, concentrazione, parametri e definizione della sessione. Il gate è volutamente binario: un risultato promettente non sostituisce un requisito operativo mancante.",
                },
                {"id": "gate_table", "type": "table", "tableId": "tb_scorecard"},
                {
                    "id": "scope",
                    "type": "markdown",
                    "body": "## Perimetro, dati e definizioni\n\n**Campione:** 22 recent mover, 15 segnali regular-only tra aprile e luglio 2026. **Trade:** ingresso alla open della barra successiva al hold, stop sotto pullback, target +20%. **Costi:** da 24 a 200 bps round-trip. **Ritardo:** zero, una o due barre complete da 15 minuti con riapplicazione dei guardrail. **Liquidità:** quota del volume della sola barra d'ingresso, non order-book o bid/ask. **Out-of-sample:** zero, perché le regole sono state modificate dopo l'ispezione di CLRO e INOD.",
                },
                {
                    "id": "method",
                    "type": "markdown",
                    "body": "## Metodo riproducibile\n\nIl notebook ricalcola causalmente segnali e uscite dalla cache, esegue stress di costi e latenza, nove scenari one-at-a-time, split cronologico, bootstrap deterministico e diagnostica di partecipazione. Gli intenti d'ordine sono broker-neutral, `DRY_RUN_ONLY` e `transmit=false`; nessun codice invia ordini.",
                },
                {
                    "id": "platform",
                    "type": "markdown",
                    "body": "## IBKR è la destinazione giusta per il prossimo esperimento\n\nLa TWS API ufficiale espone Python, market data, ordini e callback; i bracket order consentono di coordinare parent, target e stop tramite il flag `Transmit`. Il paper account usa però fill simulati top-of-book e non replica completamente il live. MetaTrader 5 espone barre, tick, book, `order_check` e `order_send`, ma l'idoneità alle small-cap USA dipende dal broker MT5 e dal tipo di strumento offerto.\n\nIl prossimo sistema deve quindi essere un adapter IBKR paper con riconciliazione, partial fill, halt, reconnect, duplicate-order prevention e kill switch; non un semplice wrapper di `placeOrder`.",
                },
                {
                    "id": "limits",
                    "type": "markdown",
                    "body": "## Limiti e incertezza\n\nIl bootstrap assume implicitamente scambiabilità dei trade e resta descrittivo; i segnali condividono regime e processo di selezione. Yahoo non fornisce quote bid/ask, order book, halt affidabili o storia point-in-time pluriennale. La partecipazione alla barra non misura la coda degli ordini. L'overlap esatto tra setup regular ed extended è solo 26,1%, quindi anche la definizione del livello resta fragile.",
                },
                {
                    "id": "next",
                    "type": "markdown",
                    "body": "## Passi raccomandati\n\n1. Aggiungere al motore un filtro di partecipazione massimo dell'1% e ordini limit.\n2. Implementare l'adapter IBKR in sola modalità shadow, registrando bid/ask, decisione e fill teorico.\n3. Passare a IBKR paper per almeno 50 segnali e misurare slippage, reject e partial fill.\n4. Acquisire almeno due anni point-in-time SIP e congelare i parametri prima del test.\n5. Considerare il live minimo solo dopo il superamento di tutti i gate, non dopo un singolo mese profittevole.",
                },
                {
                    "id": "questions",
                    "type": "markdown",
                    "body": "## Domande aperte\n\nQual è il capitale iniziale reale, quindi il limite di capacità? Si vuole tradare soltanto la sessione regolare o anche il pre-market? Quale sottoscrizione dati IBKR/SIP sarà disponibile? Queste tre risposte determinano sizing, universo osservabile e tipo di ordine, ma non cambiano l'attuale decisione di non andare live.",
                },
            ],
        },
        "snapshot": {
            "version": 1,
            "generatedAt": GENERATED_AT,
            "status": "ready",
            "datasets": {
                "summary": [summary],
                "stress_zero_delay": records(stress_zero_delay),
                "sensitivity": records(sensitivity),
                "liquidity": records(liquidity),
                "scorecard": records(scorecard),
            },
        },
        "sources": sources,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "artifact.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
