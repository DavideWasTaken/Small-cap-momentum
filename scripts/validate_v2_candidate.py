from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import pandas as pd

from smallcap_bt.backtest import simulate_exit
from smallcap_bt.config import load_config
from smallcap_bt.data import load_cache
from smallcap_bt.robustness import bootstrap_mean_ci, trade_statistics
from smallcap_bt.strategy import scan_signals


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate frozen v2 candidate across costs and periods.")
    parser.add_argument("--config", default="configs/strategy_v2_candidate.yaml")
    parser.add_argument("--windows", default="outputs/historical_5y/intraday_windows.csv")
    parser.add_argument("--data-dir", default="data/historical_alpaca_sip")
    parser.add_argument("--output-dir", default="outputs/v2_candidate")
    args = parser.parse_args()

    cfg = load_config(args.config)
    windows = pd.read_csv(args.windows)
    signal_map = {}
    for row in windows.itertuples(index=False):
        frame = load_cache(Path(args.data_dir) / f"{row.window_id}.csv", cfg.data.timezone)
        allowed = set(str(row.event_sessions).split(";"))
        for signal in scan_signals(row.ticker, frame, cfg.data, cfg.strategy):
            if signal.spike_session.isoformat() in allowed:
                signal_map[(signal.ticker, signal.spike_session, signal.trigger_session)] = (signal, frame)

    metric_rows = []
    annual_rows = []
    bootstrap_rows = []
    ledger_rows = []
    for cost in [24.0, 50.0, 100.0, 200.0]:
        stressed = replace(cfg, risk=replace(cfg.risk, slippage_bps_per_side=cost / 2, commission_bps_per_side=0.0))
        trades = [simulate_exit(signal, frame, stressed, "target_12") for signal, frame in signal_map.values()]
        trades = [trade for trade in trades if trade is not None]
        for trade in trades:
            ledger_rows.append({"total_cost_bps": cost, **trade.to_dict()})
        groups = {
            "development_2021_2023": [x for x in trades if x.entry_time.year <= 2023],
            "validation_2024": [x for x in trades if x.entry_time.year == 2024],
            "test_2025": [x for x in trades if x.entry_time.year == 2025],
            "shadow_2026": [x for x in trades if x.entry_time.year == 2026],
            "primary_2021_2025": [x for x in trades if x.entry_time.year <= 2025],
        }
        for period, chosen in groups.items():
            metric_rows.append({"period": period, "total_cost_bps": cost, **trade_statistics(chosen)})
        for year in sorted({x.entry_time.year for x in trades}):
            chosen = [x for x in trades if x.entry_time.year == year]
            annual_rows.append({"year": year, "total_cost_bps": cost, **trade_statistics(chosen)})
        primary_returns = [x.return_pct for x in groups["primary_2021_2025"]]
        bootstrap_rows.append({"period": "primary_2021_2025", "total_cost_bps": cost, **bootstrap_mean_ci(primary_returns)})

    metrics = pd.DataFrame(metric_rows)
    annual = pd.DataFrame(annual_rows)
    bootstrap = pd.DataFrame(bootstrap_rows)
    primary = metrics[(metrics.period == "primary_2021_2025") & (metrics.total_cost_bps == 100)].iloc[0]
    shadow = metrics[(metrics.period == "shadow_2026") & (metrics.total_cost_bps == 100)].iloc[0]
    boot = bootstrap[bootstrap.total_cost_bps == 100].iloc[0]
    annual100 = annual[(annual.total_cost_bps == 100) & (annual.year <= 2025)]
    positive_years = int((annual100.expectancy_filled_pct > 0).sum())
    gates = [
        {"gate": "at least 100 primary trades", "observed": int(primary.filled_trades), "required": ">= 100", "pass": bool(primary.filled_trades >= 100)},
        {"gate": "profit factor at 100 bps", "observed": float(primary.profit_factor), "required": ">= 1.30", "pass": bool(primary.profit_factor >= 1.30)},
        {"gate": "median at 100 bps", "observed": float(primary.median_return_pct), "required": "> 0", "pass": bool(primary.median_return_pct > 0)},
        {"gate": "bootstrap lower bound", "observed": float(boot.ci_low_pct), "required": ">= 0", "pass": bool(boot.ci_low_pct >= 0)},
        {"gate": "positive years 2021-2025", "observed": positive_years, "required": ">= 4 of 5", "pass": bool(positive_years >= 4)},
        {"gate": "shadow 2026 expectancy", "observed": float(shadow.expectancy_filled_pct), "required": "> 0", "pass": bool(shadow.expectancy_filled_pct > 0)},
    ]
    verdict = {
        "verdict": "V2_CANDIDATE_NOT_CONFIRMED",
        "signals": len(signal_map),
        "primary_100bps": {
            "trades": int(primary.filled_trades),
            "win_rate": float(primary.win_rate),
            "profit_factor": float(primary.profit_factor),
            "expectancy_pct": float(primary.expectancy_filled_pct),
            "median_return_pct": float(primary.median_return_pct),
            "bootstrap_ci_low_pct": float(boot.ci_low_pct),
            "bootstrap_ci_high_pct": float(boot.ci_high_pct),
            "positive_years": positive_years,
        },
        "shadow_2026_100bps": {
            "trades": int(shadow.filled_trades),
            "profit_factor": float(shadow.profit_factor),
            "expectancy_pct": float(shadow.expectancy_filled_pct),
            "median_return_pct": float(shadow.median_return_pct),
        },
        "gates_passed": sum(row["pass"] for row in gates),
        "gates_total": len(gates),
        "live_ready": False,
    }

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(output / "cost_metrics.csv", index=False)
    annual.to_csv(output / "annual_metrics.csv", index=False)
    bootstrap.to_csv(output / "bootstrap.csv", index=False)
    pd.DataFrame(gates).to_csv(output / "gates.csv", index=False)
    pd.DataFrame(ledger_rows).to_csv(output / "trades.csv", index=False)
    (output / "verdict.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    print(json.dumps(verdict, indent=2))
    print(pd.DataFrame(gates).to_string(index=False))


if __name__ == "__main__":
    main()
