# Scelta dei dati intraday

Stato verificato l’11 luglio 2026. Prezzi e piani possono cambiare: controllare sempre la documentazione ufficiale prima di acquistare.

## yfinance

Buono per il prototipo recente e per controlli visivi rapidi. Non è adatto come unica fonte per un backtest small-cap definitivo: storia 15m breve, nessuna garanzia di point-in-time completeness e volume extended-hours anomalo nel campione.

## Alpaca

Il provider è già implementato in `data.py`. La documentazione ufficiale dichiara storico azionario dal 2016. Il real-time gratuito è IEX e rappresenta solo una quota del mercato; la FAQ ufficiale indica che le query SIP storiche con `end` più vecchio di 15 minuti sono accessibili senza l'abbonamento real-time. L'accesso richiede comunque chiavi market-data gratuite. Per questa strategia il SIP storico è preferibile, perché volume e microstruttura delle small-cap sono parte del segnale.

- Piani e copertura: https://docs.alpaca.markets/us/docs/about-market-data-api
- Historical API: https://docs.alpaca.markets/us/docs/historical-api
- Feed azionari: https://docs.alpaca.markets/us/v1.1/docs/historical-stock-data-1

## Polygon

Il provider REST per aggregate bars è già implementato. Polygon offre anche flat file di minute aggregates per l’intero mercato USA; la documentazione indica, a seconda del piano, 5 anni, 10 anni o tutta la storia disponibile. È interessante per uno screener cross-sectional ampio, perché evita migliaia di richieste per singolo ticker.

- Minute aggregates flat files: https://polygon.io/docs/flat-files/stocks/minute-aggregates/2009/03

## Ordine consigliato

1. yfinance per debug e test di regressione CLRO.
2. Alpaca SIP per un primo backtest pluriennale con API semplice.
3. Polygon flat files quando serve uno screening giornaliero sull’intero mercato e un archivio locale point-in-time.

Qualunque provider venga scelto, conservare snapshot immutabili, symbol master storico, corporate actions, delisting e log di qualità. Un universo corrente applicato al passato non elimina il survivorship bias.
