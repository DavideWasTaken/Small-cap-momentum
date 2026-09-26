from __future__ import annotations

import numpy as np
import pandas as pd

from smallcap_bt.monthly_momentum import (
    circular_block_bootstrap_mean_difference,
    month_end_returns,
    parse_french_value_weighted_monthly,
    performance_metrics,
)


def test_parse_french_monthly_table() -> None:
    text = """metadata
  Average Value Weighted Returns -- Monthly
,SMALL LoPRIOR,SMALL HiPRIOR
202501,  1.00,  2.00
202502, -3.00,  4.00

  Average Equal Weighted Returns -- Monthly
"""
    frame = parse_french_value_weighted_monthly(text)
    assert list(frame.columns) == ["SMALL LoPRIOR", "SMALL HiPRIOR"]
    assert frame.index[0] == pd.Timestamp("2025-01-31")
    assert frame.iloc[1, 0] == -0.03
    assert frame.iloc[1, 1] == 0.04


def test_month_end_returns_uses_previous_month_end() -> None:
    prices = pd.Series(
        [100.0, 105.0, 110.0],
        index=pd.to_datetime(["2025-01-31", "2025-02-28", "2025-03-31"]),
        name="TEST",
    )
    returns = month_end_returns(prices)
    assert np.isnan(returns.iloc[0, 0])
    assert np.isclose(returns.iloc[1, 0], 0.05)
    assert np.isclose(returns.iloc[2, 0], 110 / 105 - 1)


def test_performance_metrics_and_block_bootstrap_are_deterministic() -> None:
    index = pd.date_range("2020-01-31", periods=24, freq="ME")
    returns = pd.Series([0.02, -0.01] * 12, index=index)
    metrics = performance_metrics(returns, pd.Series(0.0, index=index))
    assert metrics["months"] == 24
    assert metrics["max_drawdown"] < 0
    first = circular_block_bootstrap_mean_difference(returns, samples=500, block_months=6, seed=7)
    second = circular_block_bootstrap_mean_difference(returns, samples=500, block_months=6, seed=7)
    assert first == second
    assert np.isclose(first["mean_monthly_difference"], returns.mean())
