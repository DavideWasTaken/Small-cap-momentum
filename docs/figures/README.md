# Archived research figures

These figures visualize the original July 2026 study's aggregate results. They
are not a new backtest, a portfolio equity curve or a claim of live performance.
The displayed `2026 YTD` period ends at the original study cutoff; it does not
update with today's date. The aggregate tables do not establish the exact final
trading day.

## Sources and units

| Bundled table | Original archived output | Columns retained |
| --- | --- | --- |
| [historical-comparison.csv](data/historical-comparison.csv) | `strategy_decision/comparison_metrics.csv` | Case, trade count, profit factor, mean and median per-trade return |
| [historical-cost-sensitivity.csv](data/historical-cost-sensitivity.csv) | `strategy_decision/v2_cost_sensitivity.csv` | Period, total cost, filled-trade count, mean return per filled trade |

Values are copied without recalculating the historical trades. Return columns
store decimals; the figures multiply by 100 to display percentages. Costs are
round-trip basis points: 100 bps is 1%. Only aggregate summaries are included,
not provider bars, account records or credentials.

The 100 bps comparison agrees with [the final verdict](../../VERDETTO_FINALE.md):
V1 has 83 trades and a negative mean return; V2 improves the earlier sample but
deteriorates in the subsequent 2026 window. V2 was selected after reviewing V1,
so the earlier sample is not an independent validation. Small samples,
survivorship bias and the other [research boundaries](../../README.md#research-boundaries)
remain relevant.

The repository's later cash-accounting correction is not applied retroactively
to these tables. These are trade-level results, not cash-constrained or
mark-to-market portfolio performance. Regenerating the figures only redraws the
bundled tables; reconstructing the original experiments needs the corresponding
historical market data and research configuration.

## Regenerate offline

After installing the project, run from the repository root:

```bash
python docs/figures/generate.py
```

This writes `docs/images/research-comparison.png` and
`docs/images/cost-sensitivity.png` using Matplotlib. It makes no network requests.
