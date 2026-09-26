# Strategia v2 candidata: risultato della ricerca

## Modifica proposta

La variazione più promettente conserva il concetto small-cap momentum ma rende
più selettiva la resistenza:

- cluster dei massimi entro il 2% invece del 5%;
- ricerca nella parte superiore del range (`top_quantile = 0.75`);
- almeno tre test;
- ingresso causale invariato dopo breakout, pullback e due barre di hold;
- stop fisso 5%;
- target 12%;
- costi principali 100 bps round-trip.

La configurazione eseguibile è `configs/strategy_v2_candidate.yaml`.

## Perché è migliore della v1

Nel periodo 2021–2025, a 100 bps, la candidata produce:

- 70 trade;
- win rate 54,29%;
- profit factor 1,395;
- expectancy +0,849% per trade;
- mediana +0,625%.

La v1 aveva profit factor 0,741 ed expectancy -0,782%. La modifica migliora
soprattutto la selezione dei setup: sui segnali comuni i fill sono quasi sempre
identici, mentre cambia quali cluster vengono accettati come vera resistenza.

## Perché non è ancora confermata

- Il bootstrap 95% dell'expectancy 2021–2025 è -0,528% / +2,300%: include zero.
- Sono positivi tre anni su cinque, non quattro.
- Il campione principale contiene 70 trade, sotto il gate di 100.
- Nel 2026 fino al 12 luglio: 21 trade, profit factor 0,434, expectancy -1,764%
  e mediana -2,043%.
- A 200 bps anche il periodo 2021–2025 torna negativo.

Passano soltanto due gate su sei. Il verdetto è quindi
`V2_CANDIDATE_NOT_CONFIRMED`: miglioramento storico reale, ma non evidenza
sufficiente per automazione o paper trading come strategia profittevole.

## Interpretazione corretta

La v2 è una pista di ricerca, non una strategia pronta. Il risultato 2021–2025
potrebbe essere data-snooping perché la variante è stata individuata dopo avere
osservato la debolezza della v1. Il 2026, che funge da controllo temporale
successivo, è nettamente negativo e impedisce la promozione.

## Audit di selezione temporale

Un controllo successivo ha trattato il 2021–2023 come unico development e ha
richiesto almeno 25 trade, profit factor almeno 1,30, expectancy positiva e
mediana positiva. Nessuna delle 21 combinazioni setup/rischio testate supera
tutti i criteri. Nessuna combinazione resta inoltre positiva in tutte le
finestre 2021–2023, 2024, 2025 e 2026.

La decisione complessiva è quindi archiviare anche la v2 come esperimento non
confermato, senza ulteriori ritocchi di soglia sullo stesso campione. Vedere
`VERDETTO_FINALE.md`.
