> Archived research notes, July 2026. Referenced outputs are generated locally and are not bundled in this public release. Historical figures below describe the original study; they have not been rerun from the original market-data snapshots.

# Small-cap momentum continuation backtest

Motore Python causale a 15 minuti per formalizzare il setup “recent mover → consolidamento → breakout → primo pullback che tiene”. Include yfinance, provider REST per Alpaca e Polygon, screener, quattro uscite, metriche, equity curve e grafici candlestick per trade.

## Avvio rapido

```bash
cd Small-cap-momentum
source .venv/bin/activate
pip install -e .

# 1) CLRO, livello automatico
smallcap-bt validate --config configs/clro_auto.yaml --ticker CLRO

# 1b) CLRO, test di regressione con livello noto 8,35
smallcap-bt validate --config configs/clro_validation.yaml --ticker CLRO

# 2) Screener recent movers
smallcap-bt screen --config configs/multi.yaml --tickers-file configs/tickers.txt

# 3) Backtest multi-ticker
smallcap-bt backtest --config configs/multi.yaml --tickers-file configs/tickers.txt

# 4) Automazione ampia: IWM daily screen -> candidati -> backtest 15m
smallcap-bt broad-backtest --config configs/iwm_automated.yaml --daily-period 3mo

# Sensibilità: resistenza calcolata solo sulla sessione regolare
smallcap-bt backtest --config configs/multi_regular_only.yaml --tickers-file configs/tickers.txt

# Stress test per automazione/broker usando i candidati già scaricati
smallcap-bt robustness --config configs/iwm_regular_only.yaml \
  --tickers-file outputs/iwm_automated/intraday_candidates.txt \
  --output-dir outputs/automation_readiness

# Validazione strategia a 5 anni, completamente separata dal broker
python scripts/prepare_historical_candidates.py --period 5y --reuse-daily \
  --min-avg-prior-dollar-volume 500000
python scripts/prepare_intraday_windows.py --asof 2026-07-11

# Solo API market-data: nessun endpoint ordini
export APCA_DATA_KEY_ID='...'
export APCA_DATA_SECRET_KEY='...'
python scripts/download_intraday_windows.py
python scripts/backtest_historical_windows.py

# Ricerca strutturale e validazione della candidata v2
python scripts/research_v2_setup.py
python scripts/validate_v2_candidate.py

# Momentum accademico mensile small-cap vs XSMO, MTUM e IWM
python scripts/download_monthly_momentum_data.py
python scripts/backtest_monthly_momentum.py
python scripts/analyze_monthly_momentum_costs.py
python scripts/validate_monthly_momentum.py
python scripts/build_monthly_momentum_notebook.py
python scripts/build_monthly_momentum_report.py

pytest -q
```

Usare `--refresh` per ignorare la cache CSV. I path in configurazione sono relativi alla directory del progetto.

## Verdetto storico al 12 luglio 2026

### Momentum accademico mensile vs XSMO

**Il fattore 12–2 batte XSMO prima dei costi, ma non offre un vantaggio economico
abbastanza robusto per l'automazione.** Da luglio 2019 a maggio 2026 il portafoglio small/high momentum lordo
ottiene CAGR 16,92%, Sharpe 0,674 e max drawdown -29,72%; XSMO raggiunge
rispettivamente 14,10%, 0,594 e -25,54%. Al proxy di turnover annuo one-way del
305%, il vantaggio si annulla a circa 40,4 bps all-in per lato. Con 120 ordini
mensili, 25 bps per lato e i minimi IBKR Tiered, $50k restano sotto XSMO; $100k
lo superano di appena 0,49 punti prima delle imposte e delle fee omesse. Il
bootstrap lordo include zero e il quintile più piccolo è più debole.

Verdetto: **non investire nello sviluppo IBKR per questa versione e preferire
XSMO**. Riaprire la ricerca soltanto per una variante a turnover ridotto con
turnover e fill osservati. Vedere
[MOMENTUM_ACCADEMICO.md](MOMENTUM_ACCADEMICO.md), il report
`outputs/monthly_momentum_report/report.html` e il notebook
`notebooks/monthly_smallcap_momentum.ipynb`.

### Decisione complessiva dopo l'ottimizzazione

**No-go: scartare la formalizzazione attuale e non collegarla a IBKR.** La v1 è
negativa; la candidata v2 migliora il 2021–2025 ma il bootstrap include zero e
il 2026 è nettamente negativo. Fra 21 combinazioni strutturali testate, nessuna
supera tutti i gate sul solo development 2021–2023 e nessuna resta positiva in
tutte le finestre 2021–2023, 2024, 2025 e 2026. Vedere
[VERDETTO_FINALE.md](VERDETTO_FINALE.md), il report
`outputs/strategy_decision_report/report.html` e il notebook
`notebooks/strategy_go_no_go.ipynb`.

**La strategia meccanica v1 non mostra un edge sufficiente.** Sul periodo
primario 2021–2025, target +20% e 100 bps round-trip, i risultati sono: 83 trade,
win rate 36,14%, profit factor 0,741, expectancy -0,782% e mediana -2,392% per
trade. Solo il 2023 è positivo; tutte e quattro le uscite testate hanno
expectancy negativa a 100 bps. Tutti i sei gate decisionali falliscono.

Sono state scaricate e validate 301 finestre Alpaca SIP su 301, per 373.857
barre 15 minuti e copertura completa delle 328 sessioni evento. Il verdetto è
quindi **rifiutare la v1 e non collegarla a IBKR o MetaTrader**. Si applica alla
formalizzazione congelata, non a ogni possibile strategia discrezionale di
continuation. Vedere [VERDETTO_V1.md](VERDETTO_V1.md).

### Ricerca v2

Una candidata con resistenza più stretta (cluster 2%), stop fisso 5% e target
12% migliora il 2021–2025: 70 trade, PF 1,395, expectancy +0,849% e mediana
+0,625% a 100 bps. Tuttavia il bootstrap include zero e il 2026 è nettamente
negativo (21 trade, PF 0,434, expectancy -1,764%). Passano solo due gate su sei:
la candidata **non è ancora confermata né pronta per il broker**. Dettagli in
[V2_CANDIDATE.md](V2_CANDIDATE.md).

## Risultato di sviluppo precedente al run storico

- CLRO: spike automatico il 2 luglio, resistenza automatica 8,42 con tre test; il test noto a 8,35 trova quattro test.
- Breakout alle 09:00 ET, pullback/hold 09:30–09:45, ingresso causale alla successiva open 15m: 9,4706 alle 10:00.
- Target +20% e +25% raggiunti nella barra 10:00; trailing 15% chiude alle 10:45; EOD chiude a 13,71.
- Universo manuale: 27 ticker caricati su 29; ATNF e CRKN senza dati Yahoo. Due segnali automatici in 60 giorni: NCPL e CLRO.
- Automazione IWM: 1.937 azioni USA filtrate dal file holdings corrente, 1.926 con storico daily, 22 candidati recent mover e 14 segnali extended v2 dopo il filtro anti-inseguimento.
- Sensibilità critica: la variante regular-only genera 15 segnali, ma solo 6 coppie ticker/data coincidono con la variante extended; il livello di resistenza non è ancora abbastanza stabile per uso unattended.
- Readiness broker: con 100 bps round-trip il PF regular-only scende a 1,15 e la mediana a -1,10%; la seconda metà cronologica ha expectancy -1,77%. Tutti gli 11 gate live falliscono.
- La precedente ipotesi di passare a IBKR shadow/paper è stata superata dal run pluriennale: la v1 non passa alla fase broker.
- Preparazione pluriennale senza broker: 2.259.486 righe daily su cinque anni, 331 spike dopo il filtro di liquidità pre-evento, 328 eventi completi e 301 finestre intraday da scaricare. I 12 controlli di qualità passano; non sono ancora trade.
- Il campione è troppo piccolo per inferenze sulla strategia. Leggere [ASSUNZIONI.md](ASSUNZIONI.md) prima delle metriche.

## Output

Ogni run salva nella propria cartella:

- `signals.csv`: setup e timestamp causali;
- `trades.csv`: una riga per segnale/variante di uscita;
- `metrics.csv`: win rate, profit factor, avg win/loss, expectancy, R e drawdown;
- `equity.csv` e `equity_curve.png`;
- `trades/*.png`: candele con resistenza, stop, entry ed exit;
- `data_quality.csv`, `download_errors.csv`, `run_metadata.json`;
- `recent_movers.csv` per i run universe.

Le cartelle già generate includono `outputs/clro_auto`, `outputs/clro_validation`, `outputs/multi`, `outputs/iwm_automated_v2` e `outputs/iwm_regular_only`.

Il report storico finale è `outputs/historical_report/report.html`; il notebook
riproducibile è `notebooks/historical_edge_verdict.ipynb`. Il report CLRO è
`outputs/final_report/report.html`; il report dell'automazione multi-ticker è
`outputs/automation_report/report.html`. Vedere anche [VERDETTO_V1.md](VERDETTO_V1.md),
[BROKER_DEPLOYMENT.md](BROKER_DEPLOYMENT.md) e [DATI.md](DATI.md).

## Provider dati

### yfinance

È il default e non richiede credenziali. È utile per il prototipo di circa 60 giorni; la cache evita download ripetuti.

### Alpaca

```bash
export APCA_API_KEY_ID='...'
export APCA_API_SECRET_KEY='...'
smallcap-bt validate --config configs/alpaca_example.yaml --ticker CLRO \
  --start 2025-01-01 --end 2026-07-11
```

Per mantenere separata la ricerca dal trading si possono usare `APCA_DATA_KEY_ID` e `APCA_DATA_SECRET_KEY`. Gli script pluriennali chiamano esclusivamente `https://data.alpaca.markets`; non contengono chiamate per inviare ordini.

Impostare `data.provider: alpaca` e scegliere `alpaca_feed: iex` o `sip`. Il codice pagina automaticamente le risposte e richiede date esplicite.

Per una strategia basata sul volume small-cap, il feed IEX gratuito è utile soprattutto per sviluppo; il SIP consolidato è la scelta più difendibile per la validazione.

### Polygon

```bash
export POLYGON_API_KEY='...'
smallcap-bt validate --config configs/polygon_example.yaml --ticker CLRO \
  --start 2025-01-01 --end 2026-07-11
```

Impostare `data.provider: polygon`. Anche questo provider usa aggregati raw 15m e paginazione.

## Parametri chiave

- Screening: `spike_return_pct`, `spike_volume_multiple`, `volume_lookback_days`.
- Range: `consolidation_max_range_pct`, `consolidation_min_low_vs_spike_high`.
- Livello: `resistance_tests`, `resistance_tolerance_pct`, `resistance_top_quantile`, `include_extended_setup`.
- Trigger: `breakout_buffer_pct`, `hold_tolerance_pct`, `hold_bars`, orari trigger.
- Anti-inseguimento: `max_entry_extension_pct` impedisce entry troppo lontane dalla resistenza.
- Rischio: `stop_mode`, `stop_buffer_pct`, `target_pcts`, `trailing_stop_pct`.
- Esecuzione: `slippage_bps_per_side`, `commission_bps_per_side`, `intrabar_priority`.

`level_overrides` serve per test noti e deve restare vuoto nei backtest di performance.

## Struttura

```text
src/smallcap_bt/
  data.py       provider, cache, normalizzazione e data-quality
  strategy.py   spike, consolidamento, resistenza e trigger
  backtest.py   stop/exit, trade ledger, metriche ed equity
  plotting.py   candlestick ed equity curve
  cli.py        comandi riproducibili
```

Non è consulenza finanziaria. Il progetto è uno strumento di ricerca e richiede dati migliori e validazione out-of-sample prima di qualsiasi uso operativo.
