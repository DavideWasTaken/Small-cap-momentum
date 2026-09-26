# Verdetto finale: no-go per v1 e v2

## Decisione

**Scartare la formalizzazione attuale della strategia e non collegarla a IBKR.**
La v1 non mostra edge; la v2 è una pista di ricerca selezionata ex post che non
supera il controllo temporale successivo.

## Evidenza decisiva

- V1, 2021–2025, 100 bps: 83 trade, PF 0,741, expectancy -0,782%, mediana -2,392%.
- V2, 2021–2025, 100 bps: 70 trade, PF 1,395, expectancy +0,849%, mediana +0,625%.
- V2, 2026 YTD, 100 bps: 21 trade, PF 0,434, expectancy -1,764%, mediana -2,043%.
- Il bootstrap 95% della v2 sul 2021–2025 include zero.
- Su 21 combinazioni strutturali testate, nessuna supera tutti i gate sul solo
  development 2021–2023 e nessuna resta positiva in tutte le finestre
  2021–2023, 2024, 2025 e 2026.
- La v2 passa soltanto due gate su sei ed è negativa a 200 bps anche sul
  2021–2025.

## Interpretazione

Il miglioramento della v2 non è una conferma out-of-sample: la variante è stata
individuata dopo avere osservato la debolezza della v1. Continuare a modificare
soglie sullo stesso storico aumenterebbe il multiple testing senza creare nuova
evidenza.

Il risultato non dimostra che ogni lettura discrezionale del pattern small-cap
momentum sia inefficace. Dimostra che le regole meccaniche v1/v2 presenti in
questo repository non giustificano ulteriore investimento verso il live.

## Condizioni minime per riaprire la ricerca

Una nuova v3 dovrebbe partire da un'ipotesi sostanzialmente diversa, usare un
universo point-in-time con delisted ed essere congelata prima di una finestra
realmente non osservata. Prima del paper trading dovrebbe raggiungere almeno:

1. 100 trade out-of-sample;
2. profit factor ≥ 1,30 dopo 100 bps round-trip;
3. mediana positiva;
4. limite inferiore dell'intervallo dell'expectancy sopra zero;
5. almeno quattro anni positivi su cinque.

Solo dopo questi gate avrebbe senso raccogliere almeno 50 shadow/paper fill su
IBKR per misurare spread e slippage reale. Il paper trading non può confermare
un edge che il backtest non supporta.

Il report completo è in `outputs/strategy_decision_report/report.html`; il
notebook riproducibile è `notebooks/strategy_go_no_go.ipynb`.
