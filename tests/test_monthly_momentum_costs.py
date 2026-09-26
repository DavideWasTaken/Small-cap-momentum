import pandas as pd

from scripts.analyze_monthly_momentum_costs import (
    break_even_cost_bps_per_side,
    net_metrics,
)
from smallcap_bt.monthly_momentum import performance_metrics


def test_net_metrics_decline_with_annual_drag() -> None:
    returns = pd.Series([0.02] * 24)
    risk_free = pd.Series([0.0] * 24)
    gross = performance_metrics(returns, risk_free)
    net = net_metrics(returns, risk_free, annual_drag=0.02)
    assert net["cagr"] < gross["cagr"]
    assert net["total_return"] < gross["total_return"]


def test_break_even_cost_reconciles_benchmark_cagr() -> None:
    returns = pd.Series([0.015, 0.005, 0.02, -0.01] * 18)
    risk_free = pd.Series([0.0] * len(returns))
    benchmark_cagr = net_metrics(returns, risk_free, annual_drag=0.03)["cagr"]
    turnover = 3.0
    break_even_bps = break_even_cost_bps_per_side(
        returns,
        risk_free,
        benchmark_cagr,
        turnover,
    )
    reconstructed_drag = 2.0 * turnover * break_even_bps / 10_000.0
    reconstructed_cagr = net_metrics(returns, risk_free, reconstructed_drag)["cagr"]
    assert abs(reconstructed_cagr - benchmark_cagr) < 1e-12
