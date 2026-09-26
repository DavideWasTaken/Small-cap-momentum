# Research scripts

Run scripts from the repository root after installing the package. Download scripts require network access and, for some providers, your own market-data credentials. Keep credentials in your environment; never commit a populated `.env`.

The `prepare_*`, `download_*`, `backtest_*`, `research_*`, `audit_*`, and `validate_*` scripts form the research pipeline. Several stages expect earlier outputs under `data/` and `outputs/`; those generated directories are deliberately excluded from the public repository.

The `build_*` scripts are **archived report and notebook templates for the July 2026 study**. Some narrative sections contain fixed historical figures and decisions. Rerunning them with new inputs does not automatically update every written claim. Reconcile the narrative with the newly generated tables before sharing a report.

The new cash accounting in `equity_and_metrics` is tested independently. Historical per-trade summaries remain archived observations, not a rerun of the original data or a mark-to-market portfolio backtest.
