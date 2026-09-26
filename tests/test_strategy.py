from __future__ import annotations

from datetime import date

import pandas as pd

from smallcap_bt.config import DataConfig, StrategyConfig
from smallcap_bt.strategy import build_setup, find_resistance


def test_find_resistance_uses_highest_repeated_cluster():
    index = pd.date_range("2026-01-02 09:30", periods=9, freq="15min", tz="America/New_York")
    highs = [1.10, 1.80, 1.20, 1.82, 1.25, 1.79, 1.30, 1.50, 1.20]
    frame = pd.DataFrame(
        {
            "Open": [1.0] * 9,
            "High": highs,
            "Low": [0.9] * 9,
            "Close": [1.0] * 9,
            "Volume": [100] * 9,
        },
        index=index,
    )
    cfg = StrategyConfig(
        resistance_tests=3,
        resistance_tolerance_pct=0.03,
        resistance_top_quantile=0.50,
        swing_window=1,
    )
    result = find_resistance(frame, cfg)
    assert result is not None
    level, touches = result
    assert abs(level - 1.80) < 0.02
    assert len(touches) == 3


def test_setup_ignores_every_bar_on_future_trigger_session():
    tz = "America/New_York"
    rows = [
        ("2026-01-02 09:30", 1.0, 1.0, 0.95, 1.0, 100),
        ("2026-01-05 09:30", 1.0, 1.0, 0.95, 1.0, 100),
        ("2026-01-06 09:30", 1.0, 1.0, 0.95, 1.0, 100),
        ("2026-01-07 09:30", 1.0, 2.2, 1.0, 2.0, 1000),
        ("2026-01-07 16:00", 1.6, 1.80, 1.4, 1.7, 50),
        ("2026-01-07 16:15", 1.6, 1.65, 1.5, 1.6, 50),
        ("2026-01-07 16:30", 1.7, 1.82, 1.5, 1.7, 50),
        ("2026-01-07 16:45", 1.6, 1.65, 1.5, 1.6, 50),
        ("2026-01-07 19:00", 1.7, 1.79, 1.5, 1.7, 50),
        ("2026-01-08 09:30", 1.9, 2.0, 1.75, 1.9, 500),
    ]
    columns = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
    base = pd.DataFrame(rows, columns=columns).set_index("Datetime")
    base.index = pd.DatetimeIndex(base.index).tz_localize(tz)
    future = pd.DataFrame(
        {"Open": [1.9], "High": [100.0], "Low": [1.8], "Close": [2.0], "Volume": [500]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-01-08 15:00", tz=tz)]),
    )
    data_cfg = DataConfig()
    cfg = StrategyConfig(
        min_volume_history_days=2,
        volume_lookback_days=3,
        spike_volume_multiple=5.0,
        level_overrides={"TEST": {"2026-01-08": 1.80}},
    )
    setup_before = build_setup("TEST", base, date(2026, 1, 8), data_cfg, cfg)
    setup_after = build_setup("TEST", pd.concat([base, future]).sort_index(), date(2026, 1, 8), data_cfg, cfg)
    assert setup_before is not None and setup_after is not None
    assert setup_before[1] == setup_after[1] == 1.80
    assert setup_before[4]["High"].max() == setup_after[4]["High"].max() == 1.82
