from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import pandas as pd

from smallcap_bt.backtest import (
    equity_and_metrics,
    signals_frame,
    simulate_exit,
    trades_frame,
)
from smallcap_bt.config import load_config
from smallcap_bt.data import load_cache
from smallcap_bt.robustness import bootstrap_mean_ci, trade_statistics
from smallcap_bt.strategy import scan_signals


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest pre-screened historical 15m windows.")
    parser.add_argument("--config", default="configs/strategy_v1_frozen.yaml")
    parser.add_argument("--windows", default="outputs/historical_5y/intraday_windows.csv")
    parser.add_argument("--data-dir", default="data/historical_alpaca_sip")
    parser.add_argument("--output-dir", default="outputs/historical_alpaca")
    args = parser.parse_args()

    cfg = load_config(args.config)
    windows = pd.read_csv(args.windows)
    data_dir = Path(args.data_dir)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    signal_map = {}
    errors = []
    for row in windows.itertuples(index=False):
        path = data_dir / f"{row.window_id}.csv"
        if not path.exists():
            errors.append({"window_id": row.window_id, "ticker": row.ticker, "error": "missing file"})
            continue
        try:
            frame = load_cache(path, cfg.data.timezone)
            allowed_spikes = set(str(row.event_sessions).split(";"))
            for signal in scan_signals(row.ticker, frame, cfg.data, cfg.strategy):
                if signal.spike_session.isoformat() not in allowed_spikes:
                    continue
                key = (signal.ticker, signal.spike_session, signal.trigger_session)
                signal_map[key] = (signal, frame)
        except Exception as exc:
            errors.append(
                {"window_id": row.window_id, "ticker": row.ticker, "error": f"{type(exc).__name__}: {exc}"}
            )

    signals = [value[0] for value in signal_map.values()]
    signals.sort(key=lambda value: value.entry_time)
    trades = []
    for key in sorted(signal_map, key=lambda value: signal_map[value][0].entry_time):
        signal, frame = signal_map[key]
        for variant in cfg.risk.exit_variants:
            trade = simulate_exit(signal, frame, cfg, variant)
            if trade is not None:
                trades.append(trade)

    target_trades = [trade for trade in trades if trade.variant == "target_20"]
    annual_rows = []
    for variant in cfg.risk.exit_variants:
        variant_trades = [trade for trade in trades if trade.variant == variant]
        for year in sorted({trade.entry_time.year for trade in variant_trades}):
            selected = [trade for trade in variant_trades if trade.entry_time.year == year]
            annual_rows.append({"variant": variant, "year": year, **trade_statistics(selected)})
    pd.DataFrame(annual_rows).to_csv(output / "annual_metrics.csv", index=False)
    pd.DataFrame([row for row in annual_rows if row["variant"] == "target_20"]).to_csv(
        output / "annual_target20_metrics.csv", index=False
    )

    cost_rows = []
    stressed_trade_rows = []
    annual_cost_rows = []
    primary_cost_returns = {}
    for total_cost_bps in [24.0, 50.0, 100.0, 200.0]:
        stressed_cfg = replace(
            cfg,
            risk=replace(
                cfg.risk,
                exit_variants=cfg.risk.exit_variants,
                slippage_bps_per_side=total_cost_bps / 2.0,
                commission_bps_per_side=0.0,
            ),
        )
        for variant in cfg.risk.exit_variants:
            stressed_trades = []
            for signal, frame in signal_map.values():
                trade = simulate_exit(signal, frame, stressed_cfg, variant)
                if trade is not None:
                    stressed_trades.append(trade)
            for period, selected in (
                ("all", stressed_trades),
                ("primary_2021_2025", [x for x in stressed_trades if x.entry_time.year <= 2025]),
                ("development_2026", [x for x in stressed_trades if x.entry_time.year == 2026]),
            ):
                cost_rows.append(
                    {
                        "variant": variant,
                        "period": period,
                        "total_cost_bps": total_cost_bps,
                        **trade_statistics(selected),
                    }
                )
                if period == "primary_2021_2025":
                    primary_cost_returns[(variant, total_cost_bps)] = [
                        x.return_pct for x in selected
                    ]
            for trade in stressed_trades:
                stressed_trade_rows.append(
                    {"total_cost_bps": total_cost_bps, **trade.to_dict()}
                )
            for year in sorted({trade.entry_time.year for trade in stressed_trades}):
                selected_year = [
                    trade for trade in stressed_trades if trade.entry_time.year == year
                ]
                annual_cost_rows.append(
                    {
                        "variant": variant,
                        "year": year,
                        "total_cost_bps": total_cost_bps,
                        **trade_statistics(selected_year),
                    }
                )
    cost_frame = pd.DataFrame(cost_rows)
    cost_frame.to_csv(output / "cost_stress_all_variants.csv", index=False)
    cost_frame[cost_frame.variant == "target_20"].to_csv(
        output / "cost_stress_target20.csv", index=False
    )
    pd.DataFrame(stressed_trade_rows).to_csv(
        output / "stressed_trades.csv", index=False
    )
    pd.DataFrame(annual_cost_rows).to_csv(
        output / "annual_cost_metrics.csv", index=False
    )
    bootstrap_rows = [
        {
            "period": "primary_2021_2025",
            "variant": variant,
            "total_cost_bps": cost,
            **bootstrap_mean_ci(returns),
        }
        for (variant, cost), returns in primary_cost_returns.items()
    ]
    bootstrap_frame = pd.DataFrame(bootstrap_rows)
    bootstrap_frame.to_csv(output / "bootstrap_primary_all_variants.csv", index=False)
    bootstrap_frame[bootstrap_frame.variant == "target_20"].to_csv(
        output / "bootstrap_primary_target20.csv", index=False
    )

    signals_frame(signals).to_csv(output / "signals.csv", index=False)
    trades_frame(trades).to_csv(output / "trades.csv", index=False)
    metrics, equity = equity_and_metrics(trades, cfg.risk)
    metrics.to_csv(output / "metrics.csv", index=False)
    equity.to_csv(output / "equity.csv", index=False)
    pd.DataFrame(errors).to_csv(output / "window_errors.csv", index=False)
    summary = {
        "windows_manifest": len(windows),
        "windows_loaded": len(windows) - sum(error["error"] == "missing file" for error in errors),
        "window_errors": len(errors),
        "signals": len(signals),
        "trades": len(trades),
        "primary_target20_trades": sum(
            trade.entry_time.year <= 2025 for trade in target_trades
        ),
        "order_endpoints_called": False,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({**summary, "metrics": metrics.to_dict(orient="records")}, indent=2))


if __name__ == "__main__":
    main()
