from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from smallcap_bt.backtest import simulate_exit
from smallcap_bt.config import BacktestConfig, load_config
from smallcap_bt.data import load_cache
from smallcap_bt.strategy import scan_signals


def statistics(returns: pd.Series) -> dict:
    if returns.empty:
        return {"trades": 0, "win_rate": np.nan, "profit_factor": np.nan, "expectancy_pct": np.nan, "median_return_pct": np.nan}
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    return {
        "trades": len(returns),
        "win_rate": float((returns > 0).mean()),
        "profit_factor": float(wins.sum() / -losses.sum()) if len(losses) else np.inf,
        "expectancy_pct": float(returns.mean()),
        "median_return_pct": float(returns.median()),
    }


def setup_variants(base: BacktestConfig) -> dict[str, BacktestConfig]:
    s = base.strategy
    return {
        "v1": base,
        "tight_hold": replace(base, strategy=replace(s, hold_tolerance_pct=0.01, pullback_max_above_level_pct=0.08, max_entry_extension_pct=0.10)),
        "strict_resistance": replace(base, strategy=replace(s, resistance_tolerance_pct=0.02, resistance_top_quantile=0.75)),
        "strong_consolidation": replace(base, strategy=replace(s, consolidation_max_range_pct=0.35, consolidation_min_low_vs_spike_high=0.70)),
        "fresh_setup": replace(base, strategy=replace(s, spike_lookback_max_sessions=3)),
        "regular_breakout": replace(base, strategy=replace(s, include_extended_breakout=False, trigger_start="09:30")),
        "combined_v2": replace(
            base,
            strategy=replace(
                s,
                spike_lookback_max_sessions=3,
                consolidation_max_range_pct=0.35,
                consolidation_min_low_vs_spike_high=0.70,
                resistance_tolerance_pct=0.02,
                resistance_top_quantile=0.75,
                include_extended_breakout=False,
                trigger_start="09:30",
                hold_tolerance_pct=0.01,
                pullback_max_above_level_pct=0.08,
                max_entry_extension_pct=0.10,
            ),
        ),
    }


def risk_variants(cfg: BacktestConfig) -> dict[str, tuple[BacktestConfig, str]]:
    base = replace(cfg.risk, slippage_bps_per_side=50.0, commission_bps_per_side=0.0)
    return {
        "pullback_target20": (replace(cfg, risk=replace(base, stop_mode="pullback", stop_buffer_pct=0.005, target_pcts=[0.20], exit_variants=["target_20"])), "target_20"),
        "fixed5_target12": (replace(cfg, risk=replace(base, stop_mode="fixed", fixed_stop_pct=0.05, target_pcts=[0.12], exit_variants=["target_12"])), "target_12"),
        "fixed5_eod": (replace(cfg, risk=replace(base, stop_mode="fixed", fixed_stop_pct=0.05, exit_variants=["eod"])), "eod"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Predeclared structural research variants for strategy v2.")
    parser.add_argument("--config", default="configs/strategy_v1_frozen.yaml")
    parser.add_argument("--windows", default="outputs/historical_5y/intraday_windows.csv")
    parser.add_argument("--data-dir", default="data/historical_alpaca_sip")
    parser.add_argument("--output-dir", default="outputs/v2_research")
    args = parser.parse_args()

    base = load_config(args.config)
    windows = pd.read_csv(args.windows)
    loaded = []
    for row in windows.itertuples(index=False):
        frame = load_cache(Path(args.data_dir) / f"{row.window_id}.csv", base.data.timezone)
        loaded.append((row, frame, set(str(row.event_sessions).split(";"))))

    trade_rows = []
    signal_rows = []
    for setup_name, setup_cfg in setup_variants(base).items():
        signal_map = {}
        for row, frame, allowed in loaded:
            for signal in scan_signals(row.ticker, frame, setup_cfg.data, setup_cfg.strategy):
                if signal.spike_session.isoformat() in allowed:
                    signal_map[(signal.ticker, signal.spike_session, signal.trigger_session)] = (signal, frame)
        print(f"{setup_name}: {len(signal_map)} signals", flush=True)
        for signal, _ in signal_map.values():
            signal_rows.append({"setup": setup_name, **signal.to_dict()})
        for risk_name, (risk_cfg, exit_variant) in risk_variants(setup_cfg).items():
            for signal, frame in signal_map.values():
                trade = simulate_exit(signal, frame, risk_cfg, exit_variant)
                if trade is not None:
                    trade_rows.append({"setup": setup_name, "risk": risk_name, **trade.to_dict()})

    trades = pd.DataFrame(trade_rows)
    trades["year"] = pd.to_datetime(trades.entry_time, utc=True).dt.year
    periods = {
        "development_2021_2023": trades.year <= 2023,
        "validation_2024": trades.year == 2024,
        "test_2025": trades.year == 2025,
        "shadow_2026": trades.year == 2026,
        "primary_2021_2025": trades.year <= 2025,
    }
    metric_rows = []
    for (setup, risk), group in trades.groupby(["setup", "risk"]):
        for period, mask in periods.items():
            chosen = group[mask.loc[group.index]]
            metric_rows.append({"setup": setup, "risk": risk, "period": period, **statistics(chosen.return_pct)})

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(signal_rows).to_csv(output / "signals.csv", index=False)
    trades.to_csv(output / "trades.csv", index=False)
    metrics = pd.DataFrame(metric_rows)
    metrics.to_csv(output / "metrics.csv", index=False)
    print(metrics.to_string(index=False))


if __name__ == "__main__":
    main()
