# Specifica congelata v1 — prima del backtest intraday pluriennale

Congelata l’11 luglio 2026, prima di scaricare o osservare gli esiti intraday 2021–2025.

## File immutabili del test v1

- `configs/strategy_v1_frozen.yaml`
  SHA-256: `e241a55afd89457ef8f406243b03fd0212275d2e7ecaadc165e99febf111640e`
- `outputs/historical_5y/daily_spike_events.csv`
  SHA-256: `7e1e139bb69e8a7378fd9dbbb4db3ad19e6629b16bc76b459b500f36650e2c60`
- `outputs/historical_5y/intraday_windows.csv`
  SHA-256: `d7d64796455d73e412a3cc2babb3364707165e3d320ba92ac69334ac66cd204b`

Se uno di questi file cambia, il risultato non può essere etichettato “v1 frozen”.

## Universo e screening congelati

- Holdings IWM correnti: 1.937 titoli USA validi.
- Storia daily disponibile: 1.926 ticker dal 12 luglio 2021 al 10 luglio 2026.
- Spike: rendimento aggiustato almeno +50%, volume almeno 5× la media precedente.
- Prezzo precedente: 0,50–50 USD.
- Dollar volume del giorno dello spike: almeno 1 milione USD.
- Dollar volume medio precedente: almeno 500.000 USD.
- Eventi qualificati: 331; eventi con finestra post-spike completa: 328.
- Finestre intraday fuse e predefinite: 301.

## Protocollo di valutazione

1. Il periodo aprile–luglio 2026 è **development**, perché CLRO, INOD e altri esempi sono già stati osservati.
2. Il periodo luglio 2021–dicembre 2025 è la valutazione storica primaria della v1: nessuna soglia verrà cambiata dopo averne visto gli esiti.
3. I risultati saranno mostrati complessivamente e per anno; nessun anno negativo verrà escluso.
4. Costi principali: 24, 50, 100 e 200 bps round-trip.
5. Devono essere riportati mediana, bootstrap, concentrazione dei profitti, capacità e sensibilità annuale oltre a win rate e profit factor.
6. L’universo rimane soggetto a survivorship bias perché deriva dalle holdings IWM correnti. Il risultato potrà essere incoraggiante, ma non definitivo point-in-time.
7. Se la v1 fallisce, ogni modifica crea una v2 separata. La v1 non viene riscritta.

## Regola di decisione

La v1 non viene considerata economicamente promettente se, sul periodo primario e con 100 bps complessivi, non raggiunge almeno PF 1,30, mediana positiva e limite inferiore bootstrap della media non negativo. Anche un eventuale superamento non autorizza trading live: serve successivamente un vero test forward.
