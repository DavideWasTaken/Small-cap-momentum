# Assunzioni e limiti

Questo progetto traduce in regole meccaniche una strategia originariamente discrezionale. Non è una replica esatta del processo decisionale del trader e non è una raccomandazione di investimento.

## Formalizzazione del setup

1. **Spike.** Uno spike è una sessione regolare con rendimento close-to-close almeno pari a `spike_return_pct` e volume almeno `spike_volume_multiple` volte la media delle sole sessioni precedenti. Il giorno dello spike non è tradabile.
2. **Finestra recente.** Il trigger è cercato tra 1 e 5 sessioni di borsa dopo lo spike. Sono sessioni osservate nei dati, non giorni di calendario.
3. **Consolidamento.** Parte dalle 16:00 ET del giorno dello spike e termina prima del giorno candidato. Deve rispettare un’ampiezza massima rispetto al midpoint e un minimo non inferiore a una frazione del massimo dello spike.
4. **Resistenza automatica.** Si estraggono massimi locali nella parte alta del range, si raggruppano entro una tolleranza percentuale e si sceglie il cluster ripetuto più alto. Il livello è la mediana del cluster. Questo è solo un proxy di una linea tracciata a occhio.
5. **Extended hours.** Per aderire al caso CLRO, il setup principale può usare pre-market e after-hours. La configurazione `multi_regular_only.yaml` esclude queste barre dal calcolo del range e della resistenza.
6. **Breakout.** Di default richiede una chiusura 15m sopra il livello; può avvenire in extended hours.
7. **Primo pullback.** È la prima barra regular-session successiva al breakout il cui minimo torna abbastanza vicino al livello. Se i minimi delle barre di hold violano `level × (1 - hold_tolerance_pct)`, il setup fallisce: non si aspetta un secondo pullback.
8. **Hold.** Tutte le barre di conferma devono tenere il floor di tolleranza; l’ultima deve chiudere sopra la resistenza. Il default usa due barre.
9. **Ingresso.** Avviene all’open della successiva barra regular-session con volume positivo. È una scelta anti-lookahead; un fill intrabar come 9,03 su CLRO non è ricostruibile in modo affidabile da OHLC 15m.
10. **Limite anti-inseguimento.** L’ingresso viene scartato se l’open eseguibile è oltre `max_entry_extension_pct` sopra la resistenza; il default è 20%. La regola è stata aggiunta dopo il controllo visivo di INOD, che altrimenti sarebbe stato comprato quasi 30% sopra il livello.
11. **Stress dei costi.** I test di readiness applicano un costo round-trip deterministico tra 24 e 200 bps. Non sono spread osservati e non sostituiscono quote bid/ask o replay order-book.
12. **Stress della latenza.** Un ritardo di una o due barre significa 15 o 30 minuti aggiuntivi; è un test di outage/ritardo del processo, non una stima della normale latenza dell’API broker. I guardrail di hold ed estensione vengono riapplicati al nuovo prezzo.
13. **Capacità.** La partecipazione usa il volume aggregato della barra d’ingresso e un conto teorico da 100.000 USD. Non misura posizione in coda, profondità, spread o impatto di mercato; viene usata solo come filtro minimo.
14. **Gate live.** Le soglie nel readiness scorecard sono criteri di ricerca prudenziali scelti per la promozione del progetto, non garanzie di rendimento e non regole fornite da IBKR o MetaTrader.

## Uscite ed esecuzione

- Gli stop disponibili sono sotto il minimo del pullback, sotto il livello o a percentuale fissa.
- I target sono calcolati dal prezzo di ingresso comprensivo di slippage; le varianti predefinite sono +20% e +25%.
- Il trailing stop usa solo massimi di barre già completate. Il massimo della barra corrente aggiorna lo stop solo dopo avere verificato il suo minimo.
- Se stop e target sono entrambi toccati nella stessa barra e non è noto l’ordine dei tick, il default è pessimista: stop prima.
- I gap oltre stop o target sono eseguiti all’open osservato, non al livello teorico.
- Slippage e commissioni sono costanti in basis point. Non modellano spread variabile, market impact, partial fill, halt, LULD, code di esecuzione o scarsità di liquidità. Queste omissioni sono particolarmente rilevanti nelle small-cap.
- Le quattro varianti di uscita sullo stesso segnale sono scenari alternativi, non quattro osservazioni indipendenti.

## Dati

- Yahoo/yfinance è adatto al prototipo ma non è una fonte istituzionale né point-in-time. La disponibilità intraday è breve e può cambiare.
- Al 11 luglio 2026 il download CLRO copre 15 aprile–10 luglio 2026. Lo spike rilevato è il **2 luglio**, non il 1°: close 6,4788 contro 3,22 e massimo 9,62. Il 7 luglio il massimo regular-session è 16,50.
- Yahoo assegna volume zero a quasi tutte le barre extended-hours del campione. I prezzi sono utili per una verifica visiva, ma la qualità del volume non permette di validare liquidità o partecipazione fuori orario.
- Mancano quote bid/ask, trade-by-trade, halt e venue. Una barra 15m può nascondere percorsi intrabar molto diversi.
- Si usano prezzi non aggiustati (`auto_adjust=False` / `adjustment=raw`) per preservare livelli di trading; split e corporate action devono essere controllati su storie più lunghe.
- Le barre senza scambi possono essere assenti. Il motore non riempie artificialmente gli intervalli mancanti.

## Bias

- **Lookahead:** il livello per una sessione candidata usa solo barre con data precedente. Breakout, hold e ingresso sono processati in ordine; l’ingresso è sulla barra successiva. I test automatici verificano che aggiungere una barra futura al giorno del trigger non modifichi il setup pre-market.
- **Survivorship/selection bias:** `configs/tickers.txt` è una lista manuale corrente e momentum-oriented, quindi non rappresenta un universo storico imparziale. Un vero studio richiede costituenti point-in-time, ticker delistati e corporate actions.
- **Data-snooping:** i parametri sono stati formalizzati anche osservando CLRO. Il run con override 8,35 è esclusivamente un test di regressione, non una stima out-of-sample.
- **Small sample:** il run iniziale produce due segnali automatici. Win rate, profit factor ed expectancy su due trade non hanno significato statistico.
- **Multiple testing:** confrontare molte soglie e scegliere la migliore sullo stesso campione sovrastima la performance. Servono train/validation/test temporali o walk-forward.

## Equity e metriche

- Le metriche per trade sono al netto di slippage e commissioni configurati.
- L’equity usa sizing a rischio fisso, limitato da `max_position_pct`, e aggiorna il capitale a trade chiuso.
- Il max drawdown riportato è su equity a trade chiuso, non mark-to-market intraday.
- Il simulatore di equity non riserva capitale per posizioni contemporanee; su un universo ampio serve un portfolio event engine con limiti di concorrenza. Nel campione iniziale i due trade non si sovrappongono.
- Profit factor infinito significa “nessun losing trade nel campione”, non performance illimitata.

## Cosa serve prima di usare i risultati

Per una valutazione credibile servono diversi anni di dati SIP, un universo point-in-time, controlli su delisting/corporate actions, spread e halt, analisi di sensibilità, walk-forward e almeno decine/centinaia di segnali indipendenti.

## Esito del run storico v1

Al 12 luglio 2026 sono state scaricate 301 finestre Alpaca SIP su 301 e il
motore ha prodotto 112 segnali complessivi, di cui 83 nel periodo decisionale
2021–2025. Con target +20% e 100 bps round-trip il profit factor è 0,741,
l'expectancy media -0,782% e la mediana -2,392%. Tutte le uscite hanno
expectancy negativa a 100 bps e soltanto un anno su cinque è positivo.

La decisione è rifiutare la formalizzazione v1. Il campione resta sotto il gate
di 100 trade e l'intervallo bootstrap include zero: il test non prova che la
vera expectancy sia certamente negativa. Stabilisce però che i dati osservati
non forniscono evidenza sufficiente di edge e non giustificano automazione o
paper trading come strategia candidata.

## Ricerca successiva v2

La candidata v2 è stata definita dopo avere osservato i risultati della v1.
Anche se le sue regole sono causali, il confronto fra varianti introduce
multiple testing e data-snooping. Il 2021–2025 non può quindi essere considerato
un test completamente vergine della v2. Il 2026 è usato come controllo
temporale successivo ma era già parzialmente visibile durante lo sviluppo e,
inoltre, copre soltanto l'anno fino al 12 luglio.

Il crollo della v2 nel 2026 impedisce di promuoverla. Per una conferma credibile
serve una nuova finestra temporale non utilizzata nella selezione, oppure un
secondo database storico point-in-time con universo e delisted indipendenti.
