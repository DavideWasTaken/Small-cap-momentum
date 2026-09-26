# Verdetto storico v1

## Decisione

**La strategia meccanica v1 non mostra un edge sufficiente e va rifiutata.** Non
deve essere collegata a IBKR o MetaTrader, né considerata pronta per il paper
trading come conferma di redditività.

Il verdetto riguarda la formalizzazione congelata in `FROZEN_SPEC_V1.md`. Non
dimostra che ogni strategia discrezionale di small-cap continuation sia
inefficace.

## Evidenza principale

Periodo primario 2021–2025, Alpaca SIP 15 minuti, target +20%, costo round-trip
100 bps:

- 83 trade;
- win rate 36,14%;
- profit factor 0,741;
- expectancy media -0,782% per trade;
- rendimento mediano -2,392%;
- intervallo bootstrap descrittivo 95%: -2,165% / +0,683%;
- un solo anno positivo su cinque.

Tutte e quattro le uscite testate — target +20%, target +25%, trailing stop e
fine giornata — hanno expectancy negativa a 100 bps. Tutti i sei gate
decisionali congelati falliscono.

## Qualità e limiti

Sono state caricate 301 finestre su 301, per 373.857 barre SIP, con copertura del
100% delle 328 sessioni evento. Il ledger è stato riconciliato indipendentemente
con le metriche aggregate.

Restano survivorship bias nell'universo IWM corrente, assenza di delisted
point-in-time, bid/ask, halt/LULD e tick path intrabar. Questi limiti impediscono
una conclusione universale, ma non costituiscono evidenza a favore della v1.

## Cosa fare dopo

Una eventuale v2 deve partire da una nuova ipotesi, essere congelata prima del
test e usare una conferma non riutilizzata per l'ottimizzazione. Ritoccare i
parametri sullo stesso 2021–2025 e chiamarlo “validazione” produrrebbe
data-snooping.
