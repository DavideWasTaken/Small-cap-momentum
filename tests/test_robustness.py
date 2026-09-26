from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from smallcap_bt.config import BacktestConfig
from smallcap_bt.robustness import bootstrap_mean_ci, delayed_signal
from smallcap_bt.strategy import SetupSignal


def _signal() -> SetupSignal:
    tz = "America/New_York"
    stamp = lambda value: pd.Timestamp(value, tz=tz)
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
        resistance_touch_times=(stamp("2026-01-02 16:15"),),
        resistance_source="automatic",
        breakout_time=stamp("2026-01-05 09:30"),
        pullback_start=stamp("2026-01-05 09:45"),
        pullback_end=stamp("2026-01-05 09:45"),
        pullback_low=1.75,
        signal_time=stamp("2026-01-05 09:45"),
        entry_time=stamp("2026-01-05 10:00"),
        entry_price_raw=2.0,
    )


def test_bootstrap_is_deterministic_and_contains_sample_mean():
    returns = np.array([-0.1, 0.05, 0.2, 0.03])
    first = bootstrap_mean_ci(returns, samples=2000, seed=7)
    second = bootstrap_mean_ci(returns, samples=2000, seed=7)
    assert first == second
    assert first["ci_low_pct"] < returns.mean() < first["ci_high_pct"]


def test_delayed_entry_respects_max_extension_guardrail():
    signal = _signal()
    index = pd.date_range(signal.entry_time, periods=2, freq="15min")
    frame = pd.DataFrame(
        {
            "Open": [2.0, 2.25],
            "High": [2.1, 2.30],
            "Low": [1.9, 2.20],
            "Close": [2.05, 2.28],
            "Volume": [10_000, 10_000],
        },
        index=index,
    )
    cfg = BacktestConfig()
    cfg.strategy.max_entry_extension_pct = 0.20
    shifted, reason = delayed_signal(signal, frame, cfg, delay_bars=1)
    assert shifted is None
    assert reason == "above_max_extension"
