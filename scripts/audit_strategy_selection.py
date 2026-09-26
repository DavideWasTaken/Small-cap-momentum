from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "outputs" / "historical_alpaca"
RESEARCH = ROOT / "outputs" / "v2_research"
V2 = ROOT / "outputs" / "v2_candidate"
OUTPUT = ROOT / "outputs" / "strategy_decision"

PERIODS = [
    "development_2021_2023",
    "validation_2024",
    "test_2025",
    "shadow_2026",
]


def summarize(returns: pd.Series) -> dict[str, float | int]:
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    gross_loss = float(-losses.sum())
    return {
        "trades": int(len(returns)),
        "win_rate": float((returns > 0).mean()),
        "profit_factor": float(wins.sum() / gross_loss) if gross_loss else np.inf,
        "expectancy_pct": float(returns.mean()),
        "median_return_pct": float(returns.median()),
    }


def development_audit(metrics: pd.DataFrame) -> pd.DataFrame:
    development = metrics[metrics.period.eq("development_2021_2023")].copy()
    development["enough_trades"] = development.trades.ge(25)
    development["pf_gate"] = development.profit_factor.ge(1.30)
    development["expectancy_gate"] = development.expectancy_pct.gt(0)
    development["median_gate"] = development.median_return_pct.gt(0)
    development["development_gate_pass"] = development[
        ["enough_trades", "pf_gate", "expectancy_gate", "median_gate"]
    ].all(axis=1)
    return development.sort_values(
        ["development_gate_pass", "expectancy_pct", "profit_factor"],
        ascending=[False, False, False],
    )


def stability_audit(metrics: pd.DataFrame) -> pd.DataFrame:
    scoped = metrics[metrics.period.isin(PERIODS)].copy()
    scoped["period_positive"] = scoped.expectancy_pct.gt(0) & scoped.profit_factor.gt(1)
    rows: list[dict] = []
    for (setup, risk), group in scoped.groupby(["setup", "risk"]):
        indexed = group.set_index("period")
        row: dict[str, object] = {
            "setup": setup,
            "risk": risk,
            "positive_periods": int(group.period_positive.sum()),
            "all_periods_positive": bool(group.period_positive.all() and len(group) == len(PERIODS)),
            "worst_period_expectancy_pct": float(group.expectancy_pct.min()),
        }
        for period in PERIODS:
            values = indexed.loc[period]
            row[f"{period}_trades"] = int(values.trades)
            row[f"{period}_profit_factor"] = float(values.profit_factor)
            row[f"{period}_expectancy_pct"] = float(values.expectancy_pct)
            row[f"{period}_median_return_pct"] = float(values.median_return_pct)
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["all_periods_positive", "positive_periods", "worst_period_expectancy_pct"],
        ascending=[False, False, False],
    )


def reconcile_ledgers() -> dict[str, dict[str, float | int]]:
    v1_ledger = pd.read_csv(V1 / "stressed_trades.csv")
    v1_ledger["year"] = pd.to_datetime(v1_ledger.entry_time, utc=True).dt.year
    v1_returns = v1_ledger[
        v1_ledger.variant.eq("target_20")
        & v1_ledger.total_cost_bps.eq(100)
        & v1_ledger.year.le(2025)
    ].return_pct

    v2_ledger = pd.read_csv(V2 / "trades.csv")
    v2_ledger["year"] = pd.to_datetime(v2_ledger.entry_time, utc=True).dt.year
    v2_primary = v2_ledger[v2_ledger.total_cost_bps.eq(100) & v2_ledger.year.le(2025)].return_pct
    v2_shadow = v2_ledger[v2_ledger.total_cost_bps.eq(100) & v2_ledger.year.eq(2026)].return_pct

    results = {
        "v1_primary_100bps": summarize(v1_returns),
        "v2_primary_100bps": summarize(v2_primary),
        "v2_shadow_2026_100bps": summarize(v2_shadow),
    }

    saved_v1 = json.loads((V1 / "verdict.json").read_text(encoding="utf-8"))["target20_100bps"]
    saved_v2 = json.loads((V2 / "verdict.json").read_text(encoding="utf-8"))
    assert results["v1_primary_100bps"]["trades"] == 83
    assert np.isclose(results["v1_primary_100bps"]["profit_factor"], saved_v1["profit_factor"])
    assert np.isclose(
        results["v1_primary_100bps"]["expectancy_pct"], saved_v1["expectancy_pct"]
    )
    assert results["v2_primary_100bps"]["trades"] == saved_v2["primary_100bps"]["trades"]
    assert np.isclose(
        results["v2_primary_100bps"]["profit_factor"],
        saved_v2["primary_100bps"]["profit_factor"],
    )
    assert np.isclose(
        results["v2_shadow_2026_100bps"]["expectancy_pct"],
        saved_v2["shadow_2026_100bps"]["expectancy_pct"],
    )
    return results


def main() -> None:
    metrics = pd.read_csv(RESEARCH / "metrics.csv")
    candidate_count = int(metrics[["setup", "risk"]].drop_duplicates().shape[0])
    development = development_audit(metrics)
    stability = stability_audit(metrics)
    reconciled = reconcile_ledgers()

    annual = pd.read_csv(V2 / "annual_metrics.csv")
    annual_100 = annual[annual.total_cost_bps.eq(100)].sort_values("year").copy()
    costs = pd.read_csv(V2 / "cost_metrics.csv")
    costs = costs[
        costs.period.isin(["primary_2021_2025", "shadow_2026"])
    ].sort_values(["period", "total_cost_bps"])

    decision = {
        "decision": "NO_GO_DISCARD_CURRENT_FORMULATION",
        "candidate_combinations_tested": candidate_count,
        "development_candidates_passing_all_gates": int(development.development_gate_pass.sum()),
        "candidates_positive_in_all_four_periods": int(stability.all_periods_positive.sum()),
        "v1": reconciled["v1_primary_100bps"],
        "v2_primary": reconciled["v2_primary_100bps"],
        "v2_shadow_2026": reconciled["v2_shadow_2026_100bps"],
        "v2_bootstrap_includes_zero": True,
        "v2_gates_passed": 2,
        "v2_gates_total": 6,
        "ibkr_live_ready": False,
        "interpretation": (
            "The v1 is negative. The v2 is an ex-post research candidate whose apparent "
            "2021-2025 edge is not statistically confirmed and reverses in 2026."
        ),
    }

    OUTPUT.mkdir(parents=True, exist_ok=True)
    comparison = pd.DataFrame(
        [
            {"case": "v1 · 2021–2025", **reconciled["v1_primary_100bps"]},
            {"case": "v2 · 2021–2025", **reconciled["v2_primary_100bps"]},
            {"case": "v2 · 2026 YTD", **reconciled["v2_shadow_2026_100bps"]},
        ]
    )
    comparison.to_csv(OUTPUT / "comparison_metrics.csv", index=False)
    development.to_csv(OUTPUT / "candidate_development_audit.csv", index=False)
    stability.to_csv(OUTPUT / "candidate_period_stability.csv", index=False)
    annual_100.to_csv(OUTPUT / "v2_annual_100bps.csv", index=False)
    costs.to_csv(OUTPUT / "v2_cost_sensitivity.csv", index=False)
    (OUTPUT / "decision_summary.json").write_text(
        json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(decision, indent=2))


if __name__ == "__main__":
    main()
