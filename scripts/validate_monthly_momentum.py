from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from smallcap_bt.monthly_momentum import (
    circular_block_bootstrap_mean_difference,
    performance_metrics,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "monthly_momentum"


def main() -> None:
    source = pd.read_csv(OUTPUT / "source_returns.csv", parse_dates=["Date"]).set_index("Date")
    reported = pd.read_csv(OUTPUT / "metrics.csv").set_index("series")
    direct_reported = pd.read_csv(OUTPUT / "direct_metrics.csv").set_index("series")
    quality = json.loads((OUTPUT / "data_quality.json").read_text(encoding="utf-8"))
    verdict = json.loads((OUTPUT / "verdict.json").read_text(encoding="utf-8"))
    checks: list[dict] = []

    def add(name: str, observed, expected: str, passed: bool, severity: str = "critical") -> None:
        checks.append(
            {
                "check": name,
                "observed": observed,
                "expected": expected,
                "status": "PASS" if passed else "FAIL",
                "severity": severity,
            }
        )

    add("complete common months", len(source), "157", len(source) == 157)
    add("first comparison month", source.index.min().date(), "2013-05-31", str(source.index.min().date()) == "2013-05-31")
    add("last comparison month", source.index.max().date(), "2026-05-31", str(source.index.max().date()) == "2026-05-31")
    add("duplicate months", int(source.index.duplicated().sum()), "0", not source.index.duplicated().any())
    add("missing values", int(source.isna().sum().sum()), "0", not source.isna().any().any())
    add("monthly return lower bound", float(source.min().min()), "> -1", bool((source.drop(columns="rf") > -1).all().all()))
    add("no order endpoints", quality["order_endpoints_called"], "false", quality["order_endpoints_called"] is False)

    series = {
        "Small momentum gross": source.ff_2x3_small_high,
        "Smallest-quintile momentum gross": source.ff_5x5_smallest_high,
        "MTUM": source.mtum,
        "IWM": source.iwm,
        "XSMO ticker history (mixed mandate)": source.xsmo,
        "Small momentum − 25 bps/month": source.ff_2x3_small_high - 0.0025,
        "Small momentum − 50 bps/month": source.ff_2x3_small_high - 0.0050,
        "Small momentum − 100 bps/month": source.ff_2x3_small_high - 0.0100,
    }
    for name, returns in series.items():
        recalculated = performance_metrics(returns, source.rf)
        saved = reported.loc[name]
        passed = all(
            np.isclose(recalculated[field], saved[field], rtol=0, atol=1e-12)
            for field in ["total_return", "cagr", "annualized_volatility", "sharpe", "max_drawdown"]
        )
        add(f"reconcile {name}", "exact" if passed else "mismatch", "exact", passed)

    direct = source.loc["2019-07-31":]
    add("direct comparison months", len(direct), "83", len(direct) == 83)
    add("direct comparison first month", direct.index.min().date(), "2019-07-31", str(direct.index.min().date()) == "2019-07-31")
    add("direct comparison last month", direct.index.max().date(), "2026-05-31", str(direct.index.max().date()) == "2026-05-31")
    add("XSMO current mandate cutoff recorded", quality.get("direct_benchmark_valid_from"), "2019-07-31", quality.get("direct_benchmark_valid_from") == "2019-07-31")
    direct_series = {
        "Small momentum gross": direct.ff_2x3_small_high,
        "Smallest-quintile momentum gross": direct.ff_5x5_smallest_high,
        "XSMO": direct.xsmo,
        "MTUM": direct.mtum,
        "IWM": direct.iwm,
        "Small momentum − 25 bps/month": direct.ff_2x3_small_high - 0.0025,
        "Small momentum − 50 bps/month": direct.ff_2x3_small_high - 0.0050,
        "Small momentum − 100 bps/month": direct.ff_2x3_small_high - 0.0100,
    }
    for name, returns in direct_series.items():
        recalculated = performance_metrics(returns, direct.rf)
        saved = direct_reported.loc[name]
        passed = all(
            np.isclose(recalculated[field], saved[field], rtol=0, atol=1e-12)
            for field in ["total_return", "cagr", "annualized_volatility", "sharpe", "max_drawdown"]
        )
        add(f"reconcile direct {name}", "exact" if passed else "mismatch", "exact", passed)

    cost_cagrs = [performance_metrics(source.ff_2x3_small_high - bps / 10_000, source.rf)["cagr"] for bps in [0, 25, 50, 100]]
    add("cost sensitivity is monotonic", cost_cagrs, "strictly decreasing", all(a > b for a, b in zip(cost_cagrs, cost_cagrs[1:])))
    add(
        "momentum buckets are monotonic",
        "low < neutral < high",
        "low < neutral < high CAGR",
        performance_metrics(source.ff_2x3_small_low, source.rf)["cagr"]
        < performance_metrics(source.ff_2x3_small_neutral, source.rf)["cagr"]
        < performance_metrics(source.ff_2x3_small_high, source.rf)["cagr"],
    )

    # Reasonableness check against the iShares page available on 2026-07-12:
    # official MTUM inception total return through 2026-06 was 676.86%, and the
    # official June 2026 monthly return was 8.77%. The comparison series stops in
    # May, so append that published month and allow for the partial inception month.
    implied_june_total = (1 + verdict["mtum"]["total_return"]) * (1 + 0.0877) - 1
    official_june_total = 6.7686
    relative_gap = abs(implied_june_total - official_june_total) / (1 + official_june_total)
    add("MTUM aggregate reasonableness", relative_gap, "relative wealth gap < 1%", relative_gap < 0.01)

    # Invesco reports XSMO YTD NAV return of 22.56% through 2026-05-31.
    xsmo_ytd = (1.0 + direct.loc["2026", "xsmo"]).prod() - 1.0
    xsmo_official_ytd = 0.2256
    xsmo_gap = abs(xsmo_ytd - xsmo_official_ytd)
    add("XSMO YTD reasonableness", xsmo_gap, "absolute return gap < 0.10%", xsmo_gap < 0.001)

    saved_bootstrap_xsmo = pd.read_csv(OUTPUT / "bootstrap_vs_xsmo.csv").iloc[0]
    recalculated_bootstrap_xsmo = circular_block_bootstrap_mean_difference(
        direct.ff_2x3_small_high - direct.xsmo,
        samples=20_000,
        block_months=12,
        seed=20260712,
    )
    bootstrap_fields = [
        "mean_monthly_difference",
        "annualized_arithmetic_difference",
        "ci_low_annualized_arithmetic",
        "ci_high_annualized_arithmetic",
    ]
    bootstrap_matches = all(
        np.isclose(recalculated_bootstrap_xsmo[field], saved_bootstrap_xsmo[field], rtol=0, atol=1e-12)
        for field in bootstrap_fields
    )
    add("reconcile XSMO bootstrap", "exact" if bootstrap_matches else "mismatch", "exact", bootstrap_matches)
    direct_gates = pd.read_csv(OUTPUT / "direct_gates.csv")
    add("direct gate count", len(direct_gates), "7", len(direct_gates) == 7)
    add("direct gates passed", int(direct_gates["pass"].sum()), "3", int(direct_gates["pass"].sum()) == 3)

    cost_grid = pd.read_csv(OUTPUT / "turnover_cost_grid.csv")
    break_even = pd.read_csv(OUTPUT / "cost_break_even.csv")
    capital_costs = pd.read_csv(OUTPUT / "capital_cost_scenarios.csv")
    cost_verdict = json.loads((OUTPUT / "implementation_cost_verdict.json").read_text(encoding="utf-8"))
    monotonic_groups = all(
        group.sort_values("all_in_cost_bps_per_side").net_cagr.is_monotonic_decreasing
        for _, group in cost_grid.groupby("turnover_scenario")
    )
    add("turnover cost grid is monotonic", monotonic_groups, "true", monotonic_groups)
    academic_break_even = float(
        break_even.loc[
            break_even.turnover_scenario.eq("Academic monthly momentum proxy"),
            "break_even_all_in_cost_bps_per_side",
        ].iloc[0]
    )
    annual_drag_at_break_even = 2.0 * 3.05 * academic_break_even / 10_000.0
    cagr_at_break_even = performance_metrics(
        direct.ff_2x3_small_high - annual_drag_at_break_even / 12.0,
        direct.rf,
    )["cagr"]
    xsmo_cagr = float(direct_reported.loc["XSMO", "cagr"])
    add("cost break-even reconciles XSMO", abs(cagr_at_break_even - xsmo_cagr), "absolute gap < 1e-12", abs(cagr_at_break_even - xsmo_cagr) < 1e-12)
    add("XSMO reported turnover input", cost_verdict["xsmo_reported_portfolio_turnover"], "1.15", cost_verdict["xsmo_reported_portfolio_turnover"] == 1.15)
    add("academic turnover proxy input", cost_verdict["academic_monthly_momentum_turnover_proxy"], "3.05", cost_verdict["academic_monthly_momentum_turnover_proxy"] == 3.05)
    tiered_120 = capital_costs[
        capital_costs.pricing_plan.eq("IBKR Pro Tiered")
        & capital_costs.orders_per_month.eq(120)
    ].set_index("capital_usd")
    add("optimistic 50k scenario does not beat XSMO", bool(tiered_120.loc[50_000, "beats_xsmo"]), "false", not bool(tiered_120.loc[50_000, "beats_xsmo"]))
    add("optimistic 100k scenario barely beats XSMO", float(tiered_120.loc[100_000, "cagr_gap_vs_xsmo"]), "> 0", float(tiered_120.loc[100_000, "cagr_gap_vs_xsmo"]) > 0)
    add("implementation remains not live-ready", cost_verdict["live_ready"], "false", cost_verdict["live_ready"] is False)

    frame = pd.DataFrame(checks)
    frame.to_csv(OUTPUT / "validation_checks.csv", index=False)
    summary = {
        "status": "PASS" if (frame.status == "PASS").all() else "FAIL",
        "checks": len(frame),
        "failed_checks": int((frame.status == "FAIL").sum()),
        "confidence": "Share with caveats",
        "blocking_caveat": (
            "The academic portfolio is gross, and its actual constituent-level turnover, order count, spreads and fills are unavailable. "
            "Cost scenarios support a no-live decision but cannot establish a precise realized net return."
        ),
        "benchmark_reconciliation": (
            "Yahoo adjusted-close MTUM wealth was reconciled within 1% to the official iShares inception return; "
            "XSMO 2026 YTD through May was reconciled within 0.10 percentage points to Invesco NAV performance."
        ),
        "direct_benchmark_caveat": (
            "XSMO current-index comparisons begin in July 2019 because the fund changed to the S&P SmallCap 600 Momentum Index on 2019-06-21."
        ),
        "implementation_cost_assessment": (
            "At a 305% annual one-way turnover proxy, the academic strategy must stay below roughly 40.4 bps per side all-in before tax. "
            "IBKR ticket minimums make the optimistic 120-order monthly scenario fail at USD 50k and only marginally pass at USD 100k."
        ),
    }
    (OUTPUT / "validation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(frame.to_string(index=False))


if __name__ == "__main__":
    main()
