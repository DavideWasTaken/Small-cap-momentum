from __future__ import annotations

from dataclasses import replace
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import Trade, run_backtest, simulate_exit, stop_from_signal
from .config import BacktestConfig
from .data import regular_session
from .strategy import SetupSignal, scan_signals


def trade_statistics(trades: list[Trade], eligible_signals: int | None = None) -> dict:
    """Return decision-oriented statistics for one exit variant."""
    returns = np.asarray([trade.return_pct for trade in trades], dtype=float)
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    gross_profit = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(-losses.sum()) if len(losses) else 0.0
    denominator = eligible_signals if eligible_signals is not None else len(returns)
    positive_sum = gross_profit
    top3_share = (
        float(np.sort(wins)[-3:].sum() / positive_sum) if positive_sum > 0 else np.nan
    )
    return {
        "eligible_signals": int(denominator),
        "filled_trades": int(len(returns)),
        "fill_rate": float(len(returns) / denominator) if denominator else np.nan,
        "win_rate": float((returns > 0).mean()) if len(returns) else np.nan,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else np.inf,
        "expectancy_filled_pct": float(returns.mean()) if len(returns) else np.nan,
        "expectancy_all_signals_pct": float(returns.sum() / denominator) if denominator else np.nan,
        "median_return_pct": float(np.median(returns)) if len(returns) else np.nan,
        "avg_win_pct": float(wins.mean()) if len(wins) else np.nan,
        "avg_loss_pct": float(losses.mean()) if len(losses) else np.nan,
        "top3_positive_return_share": top3_share,
    }


def bootstrap_mean_ci(
    returns: np.ndarray, samples: int = 20_000, seed: int = 20260711
) -> dict:
    """Non-parametric descriptive interval; trades are not assumed independent."""
    values = np.asarray(returns, dtype=float)
    if len(values) == 0:
        return {"samples": samples, "mean_pct": np.nan, "ci_low_pct": np.nan, "ci_high_pct": np.nan}
    rng = np.random.default_rng(seed)
    means = rng.choice(values, size=(samples, len(values)), replace=True).mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return {
        "samples": samples,
        "mean_pct": float(values.mean()),
        "ci_low_pct": float(low),
        "ci_high_pct": float(high),
    }


def delayed_signal(
    signal: SetupSignal, frame: pd.DataFrame, cfg: BacktestConfig, delay_bars: int
) -> tuple[SetupSignal | None, str]:
    """Shift execution by full 15-minute bars and re-apply entry guardrails."""
    if delay_bars == 0:
        return signal, "filled"
    day = regular_session(frame[frame.index.date == signal.trigger_session], cfg.data)
    matches = np.flatnonzero(day.index == signal.entry_time)
    if not len(matches):
        return None, "entry_bar_missing"
    position = int(matches[0]) + delay_bars
    if position >= len(day):
        return None, "after_session"
    timestamp = day.index[position]
    row = day.iloc[position]
    price = float(row.Open)
    hold_floor = signal.resistance_level * (1.0 - cfg.strategy.hold_tolerance_pct)
    if float(row.Volume) <= 0:
        return None, "zero_volume"
    if price < hold_floor:
        return None, "below_hold_floor"
    if price > signal.resistance_level * (1.0 + cfg.strategy.max_entry_extension_pct):
        return None, "above_max_extension"
    return replace(signal, entry_time=timestamp, entry_price_raw=price), "filled"


def simulate_signal_set(
    signals: list[SetupSignal],
    frames: dict[str, pd.DataFrame],
    cfg: BacktestConfig,
    *,
    total_cost_bps: float,
    delay_bars: int = 0,
    variant: str = "target_20",
) -> tuple[list[Trade], dict[str, int]]:
    """Re-simulate fixed signals under cost and latency stress."""
    stressed = replace(
        cfg,
        risk=replace(
            cfg.risk,
            exit_variants=[variant],
            slippage_bps_per_side=total_cost_bps / 2.0,
            commission_bps_per_side=0.0,
        ),
    )
    trades: list[Trade] = []
    outcomes: dict[str, int] = {}
    for signal in signals:
        shifted, status = delayed_signal(signal, frames[signal.ticker], stressed, delay_bars)
        outcomes[status] = outcomes.get(status, 0) + 1
        if shifted is None:
            continue
        trade = simulate_exit(shifted, frames[signal.ticker], stressed, variant)
        if trade is not None:
            trades.append(trade)
    return trades, outcomes


def execution_stress_table(
    signals: list[SetupSignal], frames: dict[str, pd.DataFrame], cfg: BacktestConfig
) -> pd.DataFrame:
    rows = []
    for total_cost_bps, delay_bars in product([24.0, 50.0, 100.0, 200.0], [0, 1, 2]):
        trades, outcomes = simulate_signal_set(
            signals,
            frames,
            cfg,
            total_cost_bps=total_cost_bps,
            delay_bars=delay_bars,
        )
        row = {
            "total_cost_bps": total_cost_bps,
            "delay_bars": delay_bars,
            **trade_statistics(trades, eligible_signals=len(signals)),
            "missed_above_extension": outcomes.get("above_max_extension", 0),
            "missed_below_hold": outcomes.get("below_hold_floor", 0),
            "other_missed": len(signals) - len(trades)
            - outcomes.get("above_max_extension", 0)
            - outcomes.get("below_hold_floor", 0),
        }
        rows.append(row)
    return pd.DataFrame(rows)


def parameter_sensitivity_table(
    frames: dict[str, pd.DataFrame], cfg: BacktestConfig
) -> pd.DataFrame:
    """One-at-a-time sensitivity around the frozen regular-session defaults."""
    rows = []
    scenarios = [
        ("base", 0.05, 0.04, 2, 0.20),
        ("resistance_tolerance_3pct", 0.03, 0.04, 2, 0.20),
        ("resistance_tolerance_7pct", 0.07, 0.04, 2, 0.20),
        ("hold_tolerance_2pct", 0.05, 0.02, 2, 0.20),
        ("hold_tolerance_6pct", 0.05, 0.06, 2, 0.20),
        ("hold_1_bar", 0.05, 0.04, 1, 0.20),
        ("hold_3_bars", 0.05, 0.04, 3, 0.20),
        ("max_extension_10pct", 0.05, 0.04, 2, 0.10),
        ("max_extension_15pct", 0.05, 0.04, 2, 0.15),
    ]
    for label, resistance_tolerance, hold_tolerance, hold_bars, extension in scenarios:
        strategy = replace(
            cfg.strategy,
            resistance_tolerance_pct=resistance_tolerance,
            hold_tolerance_pct=hold_tolerance,
            hold_bars=hold_bars,
            max_entry_extension_pct=extension,
        )
        scenario = replace(
            cfg,
            strategy=strategy,
            risk=replace(cfg.risk, exit_variants=["target_20"]),
        )
        signals, trades = run_backtest(frames, scenario)
        stats = trade_statistics(trades, eligible_signals=len(signals))
        rows.append(
            {
                "scenario": label,
                "resistance_tolerance_pct": resistance_tolerance,
                "hold_tolerance_pct": hold_tolerance,
                "hold_bars": hold_bars,
                "max_entry_extension_pct": extension,
                **stats,
            }
        )
    return pd.DataFrame(rows)


def liquidity_diagnostics(
    signals: list[SetupSignal], frames: dict[str, pd.DataFrame], cfg: BacktestConfig
) -> pd.DataFrame:
    """Estimate order participation using the 15-minute entry bar, not quotes."""
    rows = []
    for signal in signals:
        frame = frames[signal.ticker]
        bar = frame.loc[signal.entry_time]
        stop = stop_from_signal(signal, cfg.risk)
        per_share_risk = max(signal.entry_price_raw - stop, 1e-9)
        risk_shares = cfg.risk.initial_capital * cfg.risk.risk_per_trade / per_share_risk
        allocation_shares = (
            cfg.risk.initial_capital * cfg.risk.max_position_pct / signal.entry_price_raw
        )
        shares = int(max(0.0, min(risk_shares, allocation_shares)))
        bar_volume = float(bar.Volume)
        notional = shares * signal.entry_price_raw
        bar_dollar_volume = bar_volume * float(bar.Close)
        rows.append(
            {
                "ticker": signal.ticker,
                "entry_time": signal.entry_time.isoformat(),
                "entry_price": signal.entry_price_raw,
                "shares_at_100k": shares,
                "position_notional": notional,
                "entry_bar_volume": bar_volume,
                "entry_bar_dollar_volume": bar_dollar_volume,
                "participation_of_15m_volume": shares / bar_volume if bar_volume > 0 else np.inf,
                "entry_bar_range_pct": (float(bar.High) - float(bar.Low)) / float(bar.Open),
            }
        )
    return pd.DataFrame(rows)


def chronological_split_table(trades: list[Trade]) -> pd.DataFrame:
    ordered = sorted(trades, key=lambda trade: trade.entry_time)
    if not ordered:
        return pd.DataFrame()
    split = len(ordered) // 2
    rows = []
    for label, values in (("early_half", ordered[:split]), ("late_half", ordered[split:])):
        rows.append({"period": label, **trade_statistics(values)})
    return pd.DataFrame(rows)


def exact_signal_overlap(left: list[SetupSignal], right: list[SetupSignal]) -> dict:
    left_keys = {(x.ticker, x.trigger_session.isoformat()) for x in left}
    right_keys = {(x.ticker, x.trigger_session.isoformat()) for x in right}
    union = left_keys | right_keys
    return {
        "left_signals": len(left_keys),
        "right_signals": len(right_keys),
        "overlap": len(left_keys & right_keys),
        "union": len(union),
        "jaccard": len(left_keys & right_keys) / len(union) if union else np.nan,
    }


def readiness_scorecard(
    stress: pd.DataFrame,
    sensitivity: pd.DataFrame,
    liquidity: pd.DataFrame,
    base_trades: list[Trade],
    overlap: dict,
) -> pd.DataFrame:
    cost_100 = stress[(stress.total_cost_bps == 100.0) & (stress.delay_bars == 0)].iloc[0]
    returns_100 = np.asarray([trade.return_pct for trade in base_trades], dtype=float) - 0.0076
    bootstrap = bootstrap_mean_ci(returns_100)
    top3 = trade_statistics(base_trades)["top3_positive_return_share"]
    robust_parameter_share = float(
        (
            (sensitivity.profit_factor >= 1.30)
            & (sensitivity.median_return_pct > 0)
        ).mean()
    )
    liquid_signal_share = float(
        (liquidity.participation_of_15m_volume <= 0.01).mean()
    ) if not liquidity.empty else 0.0
    checks = [
        ("Independent out-of-sample trades", 0.0, 100.0, ">=", True),
        ("Observed trades", float(len(base_trades)), 100.0, ">=", True),
        ("Profit factor after 100 bps", float(cost_100.profit_factor), 1.30, ">=", True),
        ("Median return after 100 bps", float(cost_100.median_return_pct), 0.0, ">", True),
        ("Bootstrap 95% lower mean after 100 bps", float(bootstrap["ci_low_pct"]), 0.0, ">", True),
        ("Top-3 share of gross profits", float(top3), 0.50, "<=", True),
        (
            "Parameter scenarios with PF >= 1.3 and positive median",
            robust_parameter_share,
            0.70,
            ">=",
            True,
        ),
        ("Signals using <= 1% of entry-bar volume", liquid_signal_share, 0.90, ">=", True),
        ("Regular/extended exact-signal overlap", float(overlap["jaccard"]), 0.70, ">=", True),
        ("IBKR paper shadow trades", 0.0, 50.0, ">=", True),
        ("Point-in-time SIP history, years", 0.0, 2.0, ">=", True),
    ]
    rows = []
    for criterion, observed, threshold, operator, blocking in checks:
        passed = {
            ">=": observed >= threshold,
            ">": observed > threshold,
            "<=": observed <= threshold,
        }[operator]
        rows.append(
            {
                "criterion": criterion,
                "observed": observed,
                "operator": operator,
                "threshold": threshold,
                "status": "PASS" if passed else "FAIL",
                "blocking_for_live": blocking,
            }
        )
    return pd.DataFrame(rows)


def dry_run_order_intents(
    signals: list[SetupSignal], cfg: BacktestConfig, account_equity: float = 100_000.0
) -> pd.DataFrame:
    """Create broker-neutral bracket intents; never transmits an order."""
    rows = []
    target_pct = cfg.risk.target_pcts[0]
    for signal in signals:
        stop = stop_from_signal(signal, cfg.risk)
        per_share_risk = max(signal.entry_price_raw - stop, 1e-9)
        shares = int(
            min(
                account_equity * cfg.risk.risk_per_trade / per_share_risk,
                account_equity * cfg.risk.max_position_pct / signal.entry_price_raw,
            )
        )
        rows.append(
            {
                "ticker": signal.ticker,
                "entry_time": signal.entry_time.isoformat(),
                "side": "BUY",
                "quantity": max(shares, 0),
                "entry_order_type": "LMT",
                "entry_reference_price": signal.entry_price_raw,
                "stop_order_type": "STP",
                "stop_price": stop,
                "target_order_type": "LMT",
                "target_price": signal.entry_price_raw * (1.0 + target_pct),
                "time_in_force": "DAY",
                "outside_rth": False,
                "transmit": False,
                "mode": "DRY_RUN_ONLY",
            }
        )
    return pd.DataFrame(rows)


def run_readiness_analysis(
    frames: dict[str, pd.DataFrame], cfg: BacktestConfig, output_dir: str | Path
) -> dict[str, pd.DataFrame]:
    """Run the full conservative automation-readiness battery and save its evidence."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    regular_cfg = replace(
        cfg,
        strategy=replace(cfg.strategy, include_extended_setup=False),
        risk=replace(cfg.risk, exit_variants=["target_20"]),
    )
    extended_cfg = replace(
        regular_cfg, strategy=replace(regular_cfg.strategy, include_extended_setup=True)
    )
    regular_signals, regular_trades = run_backtest(frames, regular_cfg)
    extended_signals = []
    for ticker, frame in frames.items():
        extended_signals.extend(scan_signals(ticker, frame, extended_cfg.data, extended_cfg.strategy))

    stress = execution_stress_table(regular_signals, frames, regular_cfg)
    sensitivity = parameter_sensitivity_table(frames, regular_cfg)
    liquidity = liquidity_diagnostics(regular_signals, frames, regular_cfg)
    split = chronological_split_table(regular_trades)
    overlap = exact_signal_overlap(regular_signals, extended_signals)
    overlap_df = pd.DataFrame([overlap])
    base_returns = np.asarray([trade.return_pct for trade in regular_trades], dtype=float)
    bootstrap_df = pd.DataFrame(
        [
            {"scenario": "base_24bps", **bootstrap_mean_ci(base_returns)},
            {
                "scenario": "production_100bps",
                **bootstrap_mean_ci(base_returns - 0.0076),
            },
        ]
    )
    scorecard = readiness_scorecard(stress, sensitivity, liquidity, regular_trades, overlap)
    intents = dry_run_order_intents(regular_signals, regular_cfg)
    results = {
        "execution_stress": stress,
        "parameter_sensitivity": sensitivity,
        "liquidity_diagnostics": liquidity,
        "chronological_split": split,
        "signal_overlap": overlap_df,
        "bootstrap_summary": bootstrap_df,
        "readiness_scorecard": scorecard,
        "dry_run_order_intents": intents,
    }
    for name, frame in results.items():
        frame.to_csv(output / f"{name}.csv", index=False)
    return results
