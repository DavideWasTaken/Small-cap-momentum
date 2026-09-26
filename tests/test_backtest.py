from __future__ import annotations

from datetime import date
from dataclasses import replace

import pandas as pd

from smallcap_bt.backtest import simulate_exit, equity_and_metrics
from smallcap_bt.config import BacktestConfig, RiskConfig
from smallcap_bt.strategy import SetupSignal


def _signal() -> SetupSignal:
    tz = "America/New_York"
    ts = lambda value: pd.Timestamp(value, tz=tz)
    return SetupSignal(
        ticker="TEST",
        spike_session=date(2026, 1, 2),
        trigger_session=date(2026, 1, 5),
        spike_high=2.0,
        spike_return_pct=1.0,
        spike_volume_multiple=10.0,
        consolidation_low=1.3,
        consolidation_high=1.8,
        consolidation_range_pct=0.32,
        resistance_level=1.8,
        resistance_tests=3,
        resistance_touch_times=(ts("2026-01-02 16:15"),),
        resistance_source="automatic",
        breakout_time=ts("2026-01-05 09:30"),
        pullback_start=ts("2026-01-05 09:45"),
        pullback_end=ts("2026-01-05 09:45"),
        pullback_low=1.75,
        signal_time=ts("2026-01-05 09:45"),
        entry_time=ts("2026-01-05 10:00"),
        entry_price_raw=2.0,
    )


def test_same_bar_stop_target_is_pessimistic():
    signal = _signal()
    index = pd.DatetimeIndex([signal.entry_time])
    frame = pd.DataFrame(
        {"Open": [2.0], "High": [2.6], "Low": [1.6], "Close": [2.2], "Volume": [1000]},
        index=index,
    )
    cfg = BacktestConfig()
    cfg.strategy.hold_bars = 1
    cfg.risk.stop_mode = "pullback"
    cfg.risk.stop_buffer_pct = 0.0
    cfg.risk.intrabar_priority = "stop"
    trade = simulate_exit(signal, frame, cfg, "target_20")
    assert trade is not None
    assert trade.exit_reason == "stop_ambiguous"
    assert trade.exit_price_raw == 1.75
    assert trade.return_pct < 0


def test_trailing_stop_updates_after_completed_bar():
    signal = _signal()
    index = pd.date_range(signal.entry_time, periods=2, freq="15min")
    frame = pd.DataFrame(
        {
            "Open": [2.0, 2.3],
            "High": [2.5, 2.4],
            "Low": [1.9, 2.0],
            "Close": [2.4, 2.1],
            "Volume": [1000, 1000],
        },
        index=index,
    )
    cfg = BacktestConfig()
    cfg.risk.stop_mode = "pullback"
    cfg.risk.stop_buffer_pct = 0.0
    cfg.risk.trailing_stop_pct = 0.10
    trade = simulate_exit(signal, frame, cfg, "trailing")
    assert trade is not None
    assert trade.exit_time == index[1]
    assert abs(trade.exit_price_raw - 2.25) < 1e-9


def _portfolio_trade(ticker, entry, exit_):
    signal = _signal()
    frame = pd.DataFrame(
        {"Open": [2.0], "High": [2.3], "Low": [1.99], "Close": [2.2], "Volume": [1000]},
        index=pd.DatetimeIndex([signal.entry_time]),
    )
    cfg = BacktestConfig()
    cfg.risk.slippage_bps_per_side = 0
    cfg.risk.commission_bps_per_side = 0
    trade = simulate_exit(signal, frame, cfg, "eod")
    return replace(trade, ticker=ticker, entry_time=pd.Timestamp(entry, tz="America/New_York"),
                   exit_time=pd.Timestamp(exit_, tz="America/New_York"))


def test_overlapping_trades_cannot_reuse_committed_capital():
    trades = [
        _portfolio_trade("A", "2026-01-05 10:00", "2026-01-05 15:00"),
        _portfolio_trade("B", "2026-01-05 11:00", "2026-01-05 12:00"),
    ]
    risk = RiskConfig(initial_capital=1000, risk_per_trade=1, max_position_pct=1,
                      commission_bps_per_side=0)
    metrics, curve = equity_and_metrics(trades, risk)
    assert abs(metrics.iloc[0].ending_equity - 1100) < 1e-9
    assert metrics.iloc[0].executed_trades == 1
    assert metrics.iloc[0].skipped_for_capital == 1


def test_partial_allocations_and_exit_order_are_chronological():
    trades = [
        _portfolio_trade("A", "2026-01-05 10:00", "2026-01-05 15:00"),
        _portfolio_trade("B", "2026-01-05 11:00", "2026-01-05 12:00"),
    ]
    risk = RiskConfig(initial_capital=1000, risk_per_trade=1, max_position_pct=0.75,
                      commission_bps_per_side=0)
    metrics, curve = equity_and_metrics(trades, risk)
    assert abs(metrics.iloc[0].ending_equity - 1100) < 1e-9
    assert metrics.iloc[0].executed_trades == 2
    times = pd.to_datetime(curve.timestamp.dropna(), utc=True)
    assert times.is_monotonic_increasing


def test_cash_is_reusable_after_exit_but_not_in_the_same_bar():
    risk = RiskConfig(initial_capital=1000, risk_per_trade=1, max_position_pct=1,
                      commission_bps_per_side=0)
    first = _portfolio_trade("A", "2026-01-05 10:00", "2026-01-05 11:00")
    same_bar = _portfolio_trade("B", "2026-01-05 11:00", "2026-01-05 12:00")
    next_bar = replace(same_bar, entry_time=same_bar.entry_time + pd.Timedelta(minutes=15))
    same, _ = equity_and_metrics([first, same_bar], risk)
    later, _ = equity_and_metrics([first, next_bar], risk)
    assert abs(same.iloc[0].ending_equity - 1100) < 1e-9
    assert abs(later.iloc[0].ending_equity - 1210) < 1e-9


def test_entry_commission_is_reserved_in_available_cash():
    trade = _portfolio_trade("A", "2026-01-05 10:00", "2026-01-05 11:00")
    commission = 0.001
    pnl = trade.exit_price - trade.entry_price - commission * (trade.entry_price + trade.exit_price)
    trade = replace(trade, pnl_per_share=pnl, return_pct=pnl / trade.entry_price)
    risk = RiskConfig(initial_capital=1000, risk_per_trade=1, max_position_pct=1,
                      commission_bps_per_side=10)
    metrics, curve = equity_and_metrics([trade], risk)
    expected = 1000 + (1000 / (trade.entry_price * (1 + commission))) * pnl
    assert abs(metrics.iloc[0].ending_equity - expected) < 1e-9
    assert abs(curve.iloc[-1].cash - expected) < 1e-9
