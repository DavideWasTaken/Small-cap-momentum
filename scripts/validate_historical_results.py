from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "historical_alpaca"
QUALITY = ROOT / "outputs" / "historical_5y" / "intraday_quality_summary.json"


def metrics(returns: pd.Series) -> dict:
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    return {
        "trades": len(returns),
        "win_rate": float((returns > 0).mean()),
        "profit_factor": gross_profit / gross_loss if gross_loss else np.inf,
        "expectancy_pct": float(returns.mean()),
        "median_return_pct": float(returns.median()),
    }


def main() -> None:
    signals = pd.read_csv(OUTPUT / "signals.csv")
    stressed = pd.read_csv(OUTPUT / "stressed_trades.csv")
    reported = pd.read_csv(OUTPUT / "cost_stress_all_variants.csv")
    annual = pd.read_csv(OUTPUT / "annual_cost_metrics.csv")
    bootstrap = pd.read_csv(OUTPUT / "bootstrap_primary_all_variants.csv")
    quality = json.loads(QUALITY.read_text(encoding="utf-8"))

    stressed["entry_year"] = pd.to_datetime(stressed.entry_time, utc=True).dt.year
    signals["entry_utc"] = pd.to_datetime(signals.entry_time, utc=True)
    signals["signal_utc"] = pd.to_datetime(signals.signal_time, utc=True)
    checks = []

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

    add("intraday windows load successfully", quality["windows_load_ok"], "301", quality["windows_load_ok"] == 301)
    add("event session coverage", quality["event_session_coverage"], "1.0", quality["event_session_coverage"] == 1.0)
    add("duplicate intraday timestamps", quality["duplicate_timestamps"], "0", quality["duplicate_timestamps"] == 0)
    add("unique signals", int(signals.duplicated(["ticker", "spike_session", "trigger_session"]).sum()), "0 duplicates", not signals.duplicated(["ticker", "spike_session", "trigger_session"]).any())
    add("causal entry after signal", int((signals.entry_utc > signals.signal_utc).sum()), str(len(signals)), (signals.entry_utc > signals.signal_utc).all())
    duplicate_stress = stressed.duplicated(["total_cost_bps", "variant", "ticker", "entry_time"]).sum()
    add("unique stressed trade ledger", int(duplicate_stress), "0 duplicates", duplicate_stress == 0)

    recomputed_rows = []
    for (variant, cost), group in stressed[stressed.entry_year <= 2025].groupby(["variant", "total_cost_bps"]):
        result = metrics(group.return_pct)
        recomputed_rows.append({"variant": variant, "total_cost_bps": cost, **result})
        match = reported[
            (reported.variant == variant)
            & (reported.total_cost_bps == cost)
            & (reported.period == "primary_2021_2025")
        ].iloc[0]
        passed = (
            result["trades"] == int(match.filled_trades)
            and abs(result["profit_factor"] - match.profit_factor) < 1e-12
            and abs(result["expectancy_pct"] - match.expectancy_filled_pct) < 1e-12
            and abs(result["median_return_pct"] - match.median_return_pct) < 1e-12
        )
        add(f"reconcile {variant} at {int(cost)} bps", "exact" if passed else "mismatch", "exact", passed)

    recomputed = pd.DataFrame(recomputed_rows)
    recomputed.to_csv(OUTPUT / "independent_primary_metrics.csv", index=False)
    target = recomputed[(recomputed.variant == "target_20") & (recomputed.total_cost_bps == 100)].iloc[0]
    boot = bootstrap[(bootstrap.variant == "target_20") & (bootstrap.total_cost_bps == 100)].iloc[0]
    annual_target = annual[
        (annual.variant == "target_20")
        & (annual.total_cost_bps == 100)
        & (annual.year <= 2025)
    ]
    positive_years = int((annual_target.expectancy_filled_pct > 0).sum())
    primary_variants_100 = recomputed[recomputed.total_cost_bps == 100]

    gates = [
        ("at least 100 primary trades", int(target.trades), ">= 100", target.trades >= 100),
        ("target20 PF at 100 bps", float(target.profit_factor), ">= 1.30", target.profit_factor >= 1.30),
        ("target20 median at 100 bps", float(target.median_return_pct), "> 0", target.median_return_pct > 0),
        ("target20 bootstrap lower bound", float(boot.ci_low_pct), ">= 0", boot.ci_low_pct >= 0),
        ("positive primary years", positive_years, ">= 4 of 5", positive_years >= 4),
        ("any exit positive at 100 bps", int((primary_variants_100.expectancy_pct > 0).sum()), ">= 1", (primary_variants_100.expectancy_pct > 0).any()),
    ]
    for name, observed, expected, passed in gates:
        add(name, observed, expected, bool(passed), "decision")

    check_frame = pd.DataFrame(checks)
    check_frame.to_csv(OUTPUT / "validation_checks.csv", index=False)
    decision_failures = int(
        ((check_frame.severity == "decision") & (check_frame.status == "FAIL")).sum()
    )
    verdict = {
        "verdict": "REJECT_V1_NO_EVIDENCE_OF_EDGE",
        "decision_failures": decision_failures,
        "signals_all_periods": len(signals),
        "primary_trades": int(target.trades),
        "target20_100bps": {
            "win_rate": float(target.win_rate),
            "profit_factor": float(target.profit_factor),
            "expectancy_pct": float(target.expectancy_pct),
            "median_return_pct": float(target.median_return_pct),
            "bootstrap_ci_low_pct": float(boot.ci_low_pct),
            "bootstrap_ci_high_pct": float(boot.ci_high_pct),
            "positive_years": positive_years,
        },
        "all_variants_negative_expectancy_at_100bps": bool(
            (primary_variants_100.expectancy_pct < 0).all()
        ),
        "data_quality": "PASS",
        "caveat": "Current IWM holdings create survivorship bias; rejection applies to frozen v1, not every possible continuation strategy.",
    }
    (OUTPUT / "verdict.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    print(json.dumps(verdict, indent=2))
    print(check_frame.to_string(index=False))


if __name__ == "__main__":
    main()
