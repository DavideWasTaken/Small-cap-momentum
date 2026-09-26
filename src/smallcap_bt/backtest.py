from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .config import BacktestConfig, RiskConfig
from .data import regular_session
from .strategy import SetupSignal, scan_signals


@dataclass(frozen=True)
class Trade:
    ticker: str
    variant: str
    spike_session: str
    trigger_session: str
    resistance_level: float
    resistance_source: str
    resistance_tests: int
    breakout_time: pd.Timestamp
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    entry_price_raw: float
    entry_price: float
    stop_price: float
    pullback_low: float
    exit_time: pd.Timestamp
    exit_price_raw: float
    exit_price: float
    exit_reason: str
    return_pct: float
    pnl_per_share: float
    r_multiple: float
    mfe_pct: float
    mae_pct: float
    bars_held: int

    def to_dict(self) -> dict:
        result = asdict(self)
        for key in ("breakout_time", "signal_time", "entry_time", "exit_time"):
            result[key] = result[key].isoformat()
        return result


def stop_from_signal(signal: SetupSignal, risk: RiskConfig) -> float:
    if risk.stop_mode == "pullback":
        return signal.pullback_low * (1.0 - risk.stop_buffer_pct)
    if risk.stop_mode == "level":
        return signal.resistance_level * (1.0 - risk.stop_buffer_pct)
    if risk.stop_mode == "fixed":
        return signal.entry_price_raw * (1.0 - risk.fixed_stop_pct)
    raise ValueError(f"Unknown stop_mode: {risk.stop_mode}")


def _target_for_variant(variant: str, risk: RiskConfig) -> float | None:
    if not variant.startswith("target_"):
        return None
    requested = float(variant.split("_", 1)[1]) / 100.0
    if not any(abs(requested - value) < 1e-9 for value in risk.target_pcts):
        raise ValueError(f"Variant {variant} is absent from target_pcts={risk.target_pcts}")
    return requested


def simulate_exit(
    signal: SetupSignal, frame: pd.DataFrame, cfg: BacktestConfig, variant: str
) -> Trade | None:
    risk = cfg.risk
    day = frame[frame.index.date == signal.trigger_session]
    day = regular_session(day, cfg.data)
    bars = day[day.index >= signal.entry_time]
    if bars.empty:
        return None
    slip = risk.slippage_bps_per_side / 10_000.0
    commission = risk.commission_bps_per_side / 10_000.0
    entry_raw = signal.entry_price_raw
    entry = entry_raw * (1.0 + slip)
    base_stop = stop_from_signal(signal, risk)
    target_pct = _target_for_variant(variant, risk)
    target = entry * (1.0 + target_pct) if target_pct is not None else None
    active_stop = base_stop
    trail_anchor = entry_raw
    exit_time = bars.index[-1]
    exit_raw = float(bars.iloc[-1]["Close"])
    reason = "eod"
    bars_held = len(bars)

    for count, (timestamp, bar) in enumerate(bars.iterrows(), start=1):
        open_, high, low = float(bar.Open), float(bar.High), float(bar.Low)
        stop_hit = low <= active_stop
        target_hit = target is not None and high >= target
        if open_ <= active_stop:
            exit_time, exit_raw, reason, bars_held = timestamp, open_, "stop_gap", count
            break
        if target is not None and open_ >= target:
            exit_time, exit_raw, reason, bars_held = timestamp, open_, "target_gap", count
            break
        if stop_hit and target_hit:
            if risk.intrabar_priority == "stop":
                exit_time, exit_raw, reason = timestamp, active_stop, "stop_ambiguous"
            else:
                exit_time, exit_raw, reason = timestamp, float(target), "target_ambiguous"
            bars_held = count
            break
        if stop_hit:
            exit_time, exit_raw, reason, bars_held = timestamp, active_stop, "stop", count
            break
        if target_hit:
            exit_time, exit_raw, reason, bars_held = timestamp, float(target), "target", count
            break
        if variant == "trailing":
            # Update only after evaluating the current bar: no assumption about
            # whether its high happened before its low.
            trail_anchor = max(trail_anchor, high)
            active_stop = max(base_stop, trail_anchor * (1.0 - risk.trailing_stop_pct))

    exit_price = exit_raw * (1.0 - slip)
    commission_cost = commission * (entry + exit_price)
    pnl_per_share = exit_price - entry - commission_cost
    return_pct = pnl_per_share / entry
    initial_risk = max(entry - base_stop, 1e-9)
    r_multiple = pnl_per_share / initial_risk
    path = bars.loc[:exit_time]
    mfe_pct = float(path["High"].max() / entry - 1.0)
    mae_pct = float(path["Low"].min() / entry - 1.0)
    return Trade(
        ticker=signal.ticker,
        variant=variant,
        spike_session=signal.spike_session.isoformat(),
        trigger_session=signal.trigger_session.isoformat(),
        resistance_level=signal.resistance_level,
        resistance_source=signal.resistance_source,
        resistance_tests=signal.resistance_tests,
        breakout_time=signal.breakout_time,
        signal_time=signal.signal_time,
        entry_time=signal.entry_time,
        entry_price_raw=entry_raw,
        entry_price=entry,
        stop_price=base_stop,
        pullback_low=signal.pullback_low,
        exit_time=exit_time,
        exit_price_raw=exit_raw,
        exit_price=exit_price,
        exit_reason=reason,
        return_pct=return_pct,
        pnl_per_share=pnl_per_share,
        r_multiple=r_multiple,
        mfe_pct=mfe_pct,
        mae_pct=mae_pct,
        bars_held=bars_held,
    )


def run_backtest(
    frames: dict[str, pd.DataFrame], cfg: BacktestConfig
) -> tuple[list[SetupSignal], list[Trade]]:
    signals: list[SetupSignal] = []
    trades: list[Trade] = []
    for ticker, frame in frames.items():
        ticker_signals = scan_signals(ticker, frame, cfg.data, cfg.strategy)
        signals.extend(ticker_signals)
        for signal in ticker_signals:
            for variant in cfg.risk.exit_variants:
                trade = simulate_exit(signal, frame, cfg, variant)
                if trade is not None:
                    trades.append(trade)
    signals.sort(key=lambda value: value.entry_time)
    trades.sort(key=lambda value: (value.variant, value.entry_time, value.ticker))
    return signals, trades


def trades_frame(trades: list[Trade]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    return pd.DataFrame([trade.to_dict() for trade in trades])


def signals_frame(signals: list[SetupSignal]) -> pd.DataFrame:
    if not signals:
        return pd.DataFrame()
    return pd.DataFrame([signal.to_dict() for signal in signals])


def equity_and_metrics(trades: list[Trade], risk: RiskConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Size positions against available cash, then settle exits chronologically.

    Bars give no intrabar execution ordering: entries at a timestamp cannot
    reuse cash from exits in that same bar. Simultaneous entries are allocated
    in ticker order. Open positions remain at cost; drawdown is realized-only,
    not a mark-to-market portfolio risk estimate. Trade-level statistics below
    describe all signals; executed/skipped counts describe the cash simulation.
    """
    rows: list[dict] = []
    curves: list[dict] = []
    variants = sorted({trade.variant for trade in trades})
    for variant in variants:
        selected = sorted(
            (trade for trade in trades if trade.variant == variant),
            key=lambda trade: (trade.entry_time, trade.ticker, trade.exit_time),
        )
        returns = np.array([trade.return_pct for trade in selected], dtype=float)
        wins = returns[returns > 0]
        losses = returns[returns < 0]
        gross_profit = float(wins.sum()) if len(wins) else 0.0
        gross_loss = float(-losses.sum()) if len(losses) else 0.0
        equity = risk.initial_capital
        cash = equity
        positions: dict[int, tuple[float, float]] = {}
        executed = 0
        skipped = 0
        peak = equity
        max_drawdown = 0.0
        curves.append(
            {"variant": variant, "timestamp": None, "trade": 0, "equity": equity, "drawdown_pct": 0.0}
        )
        events = []
        for number, trade in enumerate(selected):
            if trade.exit_time < trade.entry_time:
                raise ValueError("A trade cannot exit before entry")
            events.extend([(trade.entry_time, 0, number), (trade.exit_time, 1, number)])
        closed = 0
        for _, event_type, number in sorted(events):
            trade = selected[number]
            if event_type == 0:
                per_share_risk = max(trade.entry_price - trade.stop_price, 1e-9)
                risk_shares = equity * risk.risk_per_trade / per_share_risk
                allocation_shares = equity * risk.max_position_pct / trade.entry_price
                entry_cost = trade.entry_price * (1 + risk.commission_bps_per_side / 10_000)
                shares = max(0.0, min(risk_shares, allocation_shares, cash / entry_cost))
                if shares <= 1e-12:
                    skipped += 1
                    continue
                reserved = shares * entry_cost
                cash = max(0.0, cash - reserved)
                positions[number] = (shares, reserved)
                executed += 1
                continue
            position = positions.pop(number, None)
            if position is None:
                continue
            shares, reserved = position
            pnl = shares * trade.pnl_per_share
            cash += reserved + pnl
            equity += pnl
            closed += 1
            peak = max(peak, equity)
            drawdown = equity / peak - 1.0
            max_drawdown = min(max_drawdown, drawdown)
            curves.append(
                {
                    "variant": variant,
                    "timestamp": trade.exit_time.isoformat(),
                    "trade": closed,
                    "equity": equity,
                    "drawdown_pct": drawdown,
                    "cash": cash,
                    "committed_capital": sum(value[1] for value in positions.values()),
                }
            )
        rows.append(
            {
                "variant": variant,
                "trades": len(selected),
                "executed_trades": executed,
                "skipped_for_capital": skipped,
                "equity_basis": "realized_pnl_open_positions_at_cost",
                "win_rate": float((returns > 0).mean()) if len(returns) else np.nan,
                "profit_factor": gross_profit / gross_loss if gross_loss > 0 else np.inf,
                "avg_win_pct": float(wins.mean()) if len(wins) else np.nan,
                "avg_loss_pct": float(losses.mean()) if len(losses) else np.nan,
                "expectancy_pct": float(returns.mean()) if len(returns) else np.nan,
                "median_return_pct": float(np.median(returns)) if len(returns) else np.nan,
                "avg_r_multiple": float(np.mean([x.r_multiple for x in selected])) if selected else np.nan,
                "max_drawdown_pct": max_drawdown,
                "ending_equity": equity,
                "total_return_pct": equity / risk.initial_capital - 1.0,
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(curves)
