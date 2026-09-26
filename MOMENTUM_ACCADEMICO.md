# Momentum accademico sulle small cap

## Verdetto

**Il momentum classico batte XSMO prima dei costi, ma non conserva un vantaggio
economico abbastanza robusto da giustificare l'automazione IBKR.** Con i dati
disponibili la scelta operativa è preferire XSMO e scartare questa versione
mensile, salvo nuove prove basate su turnover e fill realmente osservati.

Il confronto principale parte il 31 luglio 2019, primo mese completo dopo il
passaggio di XSMO all'attuale S&P SmallCap 600 Momentum Index, e termina il 31
maggio 2026, per 83 osservazioni mensili:

| Serie | CAGR | Sharpe | Max drawdown | Rendimento totale |
|---|---:|---:|---:|---:|
| Small/high momentum, lordo | 16,92% | 0,674 | -29,72% | 194,79% |
| XSMO | 14,10% | 0,594 | -25,54% | 148,99% |
| MTUM | 16,48% | 0,751 | -30,17% | 187,16% |
| IWM | 10,80% | 0,452 | -30,64% | 103,25% |
| Small/high momentum, 25 bps/mese | 13,49% | 0,546 | -30,31% | 140,02% |
| Quintile più piccolo/high momentum, lordo | 10,47% | 0,412 | -32,89% | 99,10% |

La monotonicità interna è però corretta: i portafogli small-cap low, neutral e
high momentum hanno rispettivamente CAGR 6,75%, 11,76% e 14,23%. Il fattore è
quindi informativo. Contro XSMO il portafoglio lordo aggiunge 2,82 punti di CAGR
e 0,080 di Sharpe, ma perde 4,18 punti sul drawdown; a 25 bps/mese il vantaggio
di CAGR diventa -0,60 punti.

## Regola testata

- Segnale: rendimento cumulato da `t−12` a `t−2`, escludendo l'ultimo mese.
- Ribilanciamento: mensile.
- Costruzione primaria: portafogli value weighted 2×3 Size × Prior Return della
  Kenneth French Data Library; `Small HiPRIOR` usa titoli sotto la mediana NYSE
  e nel tercile momentum più alto.
- Robustezza size: portafoglio value weighted nel quintile più piccolo e nel
  quintile momentum più alto, dai portafogli 5×5.
- Benchmark primario: XSMO, ETF sull'S&P SmallCap 600 Momentum Index, expense
  ratio totale ufficiale 0,36%.
- Controlli secondari: MTUM come momentum non small-cap e IWM come beta small-cap.
- Costi: griglia turnover × costo all-in per lato, più scenari di capitale con i
  minimi per ordine IBKR Pro Tiered e Fixed.

XSMO è nato nel 2005, ma lo storico del ticker non rappresenta sempre la stessa
strategia: dal 21 giugno 2019 segue l'S&P SmallCap 600 Momentum Index; prima ha
seguito altri indici. Per questo il backtest non usa il 2005–giugno 2019 come
prova dell'attuale mandato.

Questa costruzione evita il survivorship bias che deriverebbe dall'applicare la
regola ai soli componenti IWM presenti oggi. Non equivale però a un backtest di
ordini eseguibili: i portafogli accademici sono lordi, e la definizione CRSP di
small cap non coincide con l'S&P SmallCap 600. XSMO usa momentum 12–2 corretto
per volatilità, il quintile più alto, pesi capitalizzazione × score e
ribilanciamento semestrale: è vicino all'ipotesi accademica, ma non identico.

## Robustezza

- Small momentum lordo batte XSMO in 5 dei 6 anni completi 2020–2025.
- La differenza media annualizzata small momentum meno XSMO è +2,85 punti.
- Bootstrap circolare, 20.000 campioni e blocchi di 12 mesi: intervallo 95%
  `[-3,32%; +10,23%]`, quindi include zero.
- A 25 bps/mese il CAGR scende al 13,49%, sotto il 14,10% di XSMO; a 50
  bps/mese scende al 10,16%.
- Il quintile di capitalizzazione più piccolo è peggiore di XSMO anche lordo.
- Passano 3 gate decisionali su 7.

## Commissioni, turnover e scala

Il vantaggio lordo su XSMO è 2,82 punti di CAGR. Usando il 305% annuo one-way
come proxy di turnover del momentum mensile, il costo di pareggio è **40,4 bps
all-in per lato, prima delle imposte**. La griglia produce:

| Costo per lato | CAGR netto stimato | Gap vs XSMO |
|---:|---:|---:|
| 10 bps | 16,21% | +2,12 pp |
| 25 bps | 15,17% | +1,07 pp |
| 50 bps | 13,44% | -0,66 pp |
| 100 bps | 10,05% | -4,04 pp |

Lo scenario retail usa 25 bps per lato, 120 ordini al mese e il solo minimo
IBKR Pro Tiered di $0,35 per ordine. È volutamente favorevole perché non include
fee di terzi, impatto, dati o fiscalità:

| Capitale | Minimi annui | Drag totale | CAGR netto | Gap vs XSMO |
|---:|---:|---:|---:|---:|
| $10k | $504 | 6,57% | 9,55% | -4,55 pp |
| $25k | $504 | 3,54% | 12,89% | -1,21 pp |
| $50k | $504 | 2,53% | 14,02% | -0,08 pp |
| $100k | $504 | 2,03% | 14,59% | +0,49 pp |
| $250k | $504 | 1,73% | 14,94% | +0,84 pp |

Anche a $100k il cuscinetto è troppo piccolo rispetto all'incertezza sul
turnover, sullo spread delle small cap e sul vantaggio statistico lordo, il cui
bootstrap include zero. Il confronto fiscale puntuale non è stimabile senza
regime, lotti, minusvalenze e distribuzioni; il maggiore turnover tende comunque
ad anticipare la realizzazione delle plusvalenze.

## Decisione di ricerca

**Non proseguire verso la produzione automatica.** Se l'obiettivo è ottenere
l'esposizione small-cap momentum, XSMO è la soluzione più difendibile con le
evidenze disponibili. La ricerca va riaperta soltanto per una variante a turnover
ridotto e con componenti point-in-time, delisted, vincoli ADV e paper fill. Per
rovesciare il verdetto servono costi osservati ben sotto 40,4 bps per lato e un
vantaggio netto con cuscinetto, non il semplice pareggio.

## Riproduzione

```bash
source .venv/bin/activate
python scripts/download_monthly_momentum_data.py
python scripts/backtest_monthly_momentum.py
python scripts/analyze_monthly_momentum_costs.py
python scripts/validate_monthly_momentum.py
python scripts/build_monthly_momentum_notebook.py
python scripts/build_monthly_momentum_report.py
python -m pytest -q
```

Gli output principali sono:

- `outputs/monthly_momentum_report/report.html` — report navigabile;
- `notebooks/monthly_smallcap_momentum.ipynb` — analisi eseguita e riproducibile;
- `outputs/monthly_momentum/` — serie, metriche, bootstrap, gate e controlli;
- `configs/monthly_momentum_academic.yaml` — specifica congelata.

Fonti metodologiche: [Kenneth French Data
Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_Library.html),
[dettaglio dei sei portafogli Size × Prior
Return](https://mba.tuck.dartmouth.edu/pages/faculty/ken.French/Data_Library/det_6_port_form_sz_pr_12_2.html),
le [commissioni ufficiali IBKR](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php),
il [prospetto SEC di XSMO](https://www.sec.gov/Archives/edgar/data/1209466/000119312525190429/d56632d497k.htm),
lo studio sul [turnover del momentum mensile](https://www.tandfonline.com/doi/abs/10.1080/0015198X.2024.2317323),
lo studio NBER sui [costi di trading delle anomalie](https://www.nber.org/papers/w20721.pdf),
la [pagina ufficiale Invesco
XSMO](https://www.invesco.com/us/en/financial-products/etfs/invesco-sp-smallcap-momentum-etf.html)
e la [metodologia S&P Momentum
Indices](https://www.spglobal.com/spdji/en/documents/methodologies/methodology-sp-momentum-indices.pdf).

Non è consulenza finanziaria. I risultati storici non garantiscono rendimenti
futuri.
