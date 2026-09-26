import pandas as pd

from scripts.audit_strategy_selection import development_audit, stability_audit


def _metrics() -> pd.DataFrame:
    rows = []
    for setup, risk, values in [
        ("robust", "fixed", [0.01, 0.02, 0.01, 0.005]),
        ("fragile", "fixed", [0.02, 0.01, -0.01, 0.01]),
    ]:
        for period, expectancy in zip(
            ["development_2021_2023", "validation_2024", "test_2025", "shadow_2026"],
            values,
        ):
            rows.append(
                {
                    "setup": setup,
                    "risk": risk,
                    "period": period,
                    "trades": 30,
                    "win_rate": 0.55,
                    "profit_factor": 1.4 if expectancy > 0 else 0.8,
                    "expectancy_pct": expectancy,
                    "median_return_pct": 0.005 if expectancy > 0 else -0.005,
                }
            )
    return pd.DataFrame(rows)


def test_development_audit_requires_all_gates() -> None:
    audited = development_audit(_metrics())
    assert audited.development_gate_pass.all()

    metrics = _metrics()
    metrics.loc[
        metrics.setup.eq("fragile") & metrics.period.eq("development_2021_2023"),
        "median_return_pct",
    ] = -0.001
    audited = development_audit(metrics).set_index("setup")
    assert bool(audited.loc["robust", "development_gate_pass"])
    assert not bool(audited.loc["fragile", "development_gate_pass"])


def test_stability_audit_rejects_one_negative_period() -> None:
    audited = stability_audit(_metrics()).set_index("setup")
    assert bool(audited.loc["robust", "all_periods_positive"])
    assert not bool(audited.loc["fragile", "all_periods_positive"])
    assert audited.loc["fragile", "positive_periods"] == 3
