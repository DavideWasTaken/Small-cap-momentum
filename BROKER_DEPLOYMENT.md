# Valutazione deployment: IBKR e MetaTrader 5

Stato al 11 luglio 2026: **adatto a dry-run e paper/shadow testing; non promosso al live**.

## Scelta consigliata

Per questa strategia su azioni small-cap USA, la prima integrazione dovrebbe essere **Interactive Brokers TWS API / IB Gateway**.

IBKR espone ufficialmente API Python, dati storici e live, ordini, callback di stato e bracket order. La proprietà `OutsideRth` permette di abilitare l’esecuzione fuori dalla sessione regolare quando il contratto e l’ordine lo consentono. I dati live e storici richiedono però le corrette sottoscrizioni di mercato; per uno screener ampio vanno rispettati anche pacing e limiti delle market-data lines.

Fonti ufficiali:

- [IBKR TWS API](https://ibkrcampus.com/campus/ibkr-api-page/twsapi-doc/)
- [IBKR order types e bracket order](https://ibkrcampus.com/campus/ibkr-api-page/order-types/)
- [IBKR paper trading e limiti del simulatore](https://www.interactivebrokers.com/campus/glossary-terms/paper-trading-account/)
- [IBKR historical bars](https://interactivebrokers.github.io/tws-api/historical_bars.html)

MetaTrader 5 dispone di integrazione Python ufficiale per barre, tick, book, controllo ordini e `order_send`. Tuttavia, la disponibilità delle azioni NASDAQ/NYSE, il modello di esecuzione, gli orari extended e i simboli dipendono interamente dal broker MT5 scelto. Per questa strategia MetaTrader è quindi un’opzione solo dopo aver verificato che il broker offra le azioni reali richieste, non CFD sintetici, con dati e routing adeguati.

Fonti ufficiali:

- [MetaTrader 5 Python integration](https://www.mql5.com/en/docs/python_metatrader5)
- [MetaTrader 5 `order_send`](https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py)

## Architettura proposta

```text
daily universe scan
        ↓
candidate state store
        ↓
15m live bars + causal resistance/hold engine
        ↓
pre-trade guardrails
        ↓
broker-neutral OrderIntent
        ↓
IBKR paper adapter
        ↓
order/fill callbacks + reconciliation + kill switch
```

Gli intenti generati in `outputs/automation_readiness/dry_run_order_intents.csv` sono deliberatamente marcati `DRY_RUN_ONLY` e `transmit=false`. Non esiste alcun percorso che invii ordini reali.

## Guardrail obbligatori prima del paper test

1. Usare ordini limit per l’ingresso, non market order su small-cap volatili.
2. Creare stop e target come figli/OCA solo dopo la conferma del fill della quantità effettiva.
3. Gestire partial fill, rifiuti, cancellazioni, halt, disconnessione e riconnessione.
4. Riconciliare periodicamente ordini e posizioni con il broker; lo stato locale non è fonte unica.
5. Impostare limiti giornalieri: perdita massima, numero massimo di ordini, esposizione per titolo e totale.
6. Rifiutare ordini oltre la partecipazione massima al volume e oltre il limite di estensione.
7. Salvare bid, ask, last, decisione, ordine, acknowledgement e fill per misurare lo slippage reale.
8. Avviare in shadow mode; poi paper; infine, solo dopo promozione statistica, capitale minimo.

## Criteri di promozione al live

- almeno 100 trade out-of-sample con parametri congelati;
- almeno 50 shadow/paper trade su IBKR;
- profit factor ≥1,30 dopo 100 bps di costo complessivo;
- mediana e limite inferiore bootstrap positivi;
- nessuna dipendenza dominante dai tre trade migliori;
- almeno il 90% degli ordini sotto l’1% del volume della barra d’ingresso;
- dati point-in-time SIP per almeno due anni;
- test verificati di restart, duplicate-order prevention, partial fill, halt e kill switch.
