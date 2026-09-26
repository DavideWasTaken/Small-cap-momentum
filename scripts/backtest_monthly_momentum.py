from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from smallcap_bt.monthly_momentum import (
    annual_returns,
    circular_block_bootstrap_mean_difference,
    performance_metrics,
)


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare academic small-cap momentum with MTUM and IWM.")
    parser.add_argument("--config", default="configs/monthly_momentum_academic.yaml")
    parser.add_argument("--input", default="outputs/monthly_momentum/source_returns.csv")
    parser.add_argument("--output-dir", default="outputs/monthly_momentum")
    args = parser.parse_args()

    config = yaml.safe_load((ROOT / args.config).read_text(encoding="utf-8"))
    costs = config["comparison"]["monthly_cost_bps"]
    bootstrap_cfg = config["bootstrap"]
    source = pd.read_csv(ROOT / args.input, parse_dates=["Date"]).set_index("Date")
    source.index = source.index.to_period("M").to_timestamp("M")

    series: dict[str, pd.Series] = {
        "Small momentum gross": source.ff_2x3_small_high,
        "Smallest-quintile momentum gross": source.ff_5x5_smallest_high,
        "MTUM": source.mtum,
        "IWM": source.iwm,
        "XSMO ticker history (mixed mandate)": source.xsmo,
    }
    for cost in costs:
        if cost:
            series[f"Small momentum − {cost} bps/month"] = source.ff_2x3_small_high - cost / 10_000.0

    metric_rows = []
    for name, returns in series.items():
        metric_rows.append({"series": name, **performance_metrics(returns, source.rf)})
    metrics = pd.DataFrame(metric_rows)

    equity = pd.DataFrame({name: (1.0 + returns).cumprod() for name, returns in series.items()})
    equity.index.name = "Date"
    annual = annual_returns(
        pd.DataFrame(
            {
                "Small momentum gross": source.ff_2x3_small_high,
                "Smallest-quintile momentum gross": source.ff_5x5_smallest_high,
                "MTUM": source.mtum,
                "IWM": source.iwm,
                "XSMO ticker history (mixed mandate)": source.xsmo,
            }
        )
    )
    bucket_metrics = pd.DataFrame(
        [
            {
                "bucket": label,
                **performance_metrics(source[column], source.rf),
            }
            for label, column in [
                ("Small-cap low momentum", "ff_2x3_small_low"),
                ("Small-cap neutral momentum", "ff_2x3_small_neutral"),
                ("Small-cap high momentum", "ff_2x3_small_high"),
            ]
        ]
    )

    subperiod_rows = []
    subperiods = {
        "2013-05 to 2019-12": ("2013-05-31", "2019-12-31"),
        "2020-01 to 2026-05": ("2020-01-31", "2026-05-31"),
    }
    for period, (start, end) in subperiods.items():
        for name in ["Small momentum gross", "MTUM", "IWM"]:
            chosen = series[name].loc[start:end]
            subperiod_rows.append({"period": period, "series": name, **performance_metrics(chosen, source.rf.loc[start:end])})
    subperiod_metrics = pd.DataFrame(subperiod_rows)

    bootstrap = circular_block_bootstrap_mean_difference(
        source.ff_2x3_small_high - source.mtum,
        samples=bootstrap_cfg["samples"],
        block_months=bootstrap_cfg["block_months"],
        seed=bootstrap_cfg["seed"],
    )

    direct_start = pd.Timestamp(config["comparison"]["direct_benchmark_start_month"])
    direct_source = source.loc[direct_start:].copy()
    direct_series: dict[str, pd.Series] = {
        "Small momentum gross": direct_source.ff_2x3_small_high,
        "Smallest-quintile momentum gross": direct_source.ff_5x5_smallest_high,
        "XSMO": direct_source.xsmo,
        "MTUM": direct_source.mtum,
        "IWM": direct_source.iwm,
    }
    for cost in costs:
        if cost:
            direct_series[f"Small momentum − {cost} bps/month"] = (
                direct_source.ff_2x3_small_high - cost / 10_000.0
            )
    direct_metrics = pd.DataFrame(
        [
            {"series": name, **performance_metrics(returns, direct_source.rf)}
            for name, returns in direct_series.items()
        ]
    )
    direct_equity = pd.DataFrame(
        {name: (1.0 + returns).cumprod() for name, returns in direct_series.items()}
    )
    direct_equity.index.name = "Date"
    direct_annual = annual_returns(
        pd.DataFrame(
            {
                name: direct_series[name]
                for name in [
                    "Small momentum gross",
                    "Smallest-quintile momentum gross",
                    "XSMO",
                    "MTUM",
                    "IWM",
                ]
            }
        )
    )
    bootstrap_xsmo = circular_block_bootstrap_mean_difference(
        direct_source.ff_2x3_small_high - direct_source.xsmo,
        samples=bootstrap_cfg["samples"],
        block_months=bootstrap_cfg["block_months"],
        seed=bootstrap_cfg["seed"],
    )

    direct_indexed = direct_metrics.set_index("series")
    direct_gross = direct_indexed.loc["Small momentum gross"]
    direct_smallest = direct_indexed.loc["Smallest-quintile momentum gross"]
    xsmo = direct_indexed.loc["XSMO"]
    direct_cost25 = direct_indexed.loc["Small momentum − 25 bps/month"]
    direct_full_years = direct_annual.loc[
        config["comparison"]["direct_benchmark_full_year_start"] :
        config["comparison"]["direct_benchmark_full_year_end"]
    ]
    years_beating_xsmo = int(
        (direct_full_years["Small momentum gross"] > direct_full_years.XSMO).sum()
    )
    required_years = len(direct_full_years) // 2 + 1
    direct_gates = pd.DataFrame(
        [
            {"gate": "Gross CAGR exceeds XSMO", "observed": direct_gross.cagr - xsmo.cagr, "required": "> 0", "pass": bool(direct_gross.cagr > xsmo.cagr)},
            {"gate": "Gross Sharpe exceeds XSMO", "observed": direct_gross.sharpe - xsmo.sharpe, "required": "> 0", "pass": bool(direct_gross.sharpe > xsmo.sharpe)},
            {"gate": "Gross max drawdown no worse than XSMO", "observed": direct_gross.max_drawdown - xsmo.max_drawdown, "required": ">= 0", "pass": bool(direct_gross.max_drawdown >= xsmo.max_drawdown)},
            {"gate": "25 bps/month CAGR exceeds XSMO", "observed": direct_cost25.cagr - xsmo.cagr, "required": "> 0", "pass": bool(direct_cost25.cagr > xsmo.cagr)},
            {"gate": "Beats XSMO in majority of full years", "observed": years_beating_xsmo, "required": f">= {required_years} of {len(direct_full_years)}", "pass": bool(years_beating_xsmo >= required_years)},
            {"gate": "Smallest-quintile sensitivity beats XSMO", "observed": direct_smallest.cagr - xsmo.cagr, "required": "> 0", "pass": bool(direct_smallest.cagr > xsmo.cagr)},
            {"gate": "Bootstrap lower bound vs XSMO above zero", "observed": bootstrap_xsmo["ci_low_annualized_arithmetic"], "required": "> 0", "pass": bool(bootstrap_xsmo["ci_low_annualized_arithmetic"] > 0)},
        ]
    )

    indexed = metrics.set_index("series")
    gross = indexed.loc["Small momentum gross"]
    smallest = indexed.loc["Smallest-quintile momentum gross"]
    mtum = indexed.loc["MTUM"]
    iwm = indexed.loc["IWM"]
    cost25 = indexed.loc["Small momentum − 25 bps/month"]
    full_year_start = config["comparison"]["full_year_start"]
    full_year_end = config["comparison"]["full_year_end"]
    full_years = annual.loc[full_year_start:full_year_end]
    years_beating_mtum = int((full_years["Small momentum gross"] > full_years.MTUM).sum())
    gates = pd.DataFrame(
        [
            {"gate": "Gross CAGR exceeds MTUM", "observed": gross.cagr - mtum.cagr, "required": "> 0", "pass": bool(gross.cagr > mtum.cagr)},
            {"gate": "Gross Sharpe exceeds MTUM", "observed": gross.sharpe - mtum.sharpe, "required": "> 0", "pass": bool(gross.sharpe > mtum.sharpe)},
            {"gate": "Gross max drawdown no worse than MTUM", "observed": gross.max_drawdown - mtum.max_drawdown, "required": ">= 0", "pass": bool(gross.max_drawdown >= mtum.max_drawdown)},
            {"gate": "25 bps/month CAGR exceeds IWM", "observed": cost25.cagr - iwm.cagr, "required": "> 0", "pass": bool(cost25.cagr > iwm.cagr)},
            {"gate": "Beats MTUM in majority of full years", "observed": years_beating_mtum, "required": ">= 7 of 12", "pass": bool(years_beating_mtum >= 7)},
            {"gate": "Smallest-quintile sensitivity beats IWM", "observed": smallest.cagr - iwm.cagr, "required": "> 0", "pass": bool(smallest.cagr > iwm.cagr)},
            {"gate": "Bootstrap lower bound vs MTUM above zero", "observed": bootstrap["ci_low_annualized_arithmetic"], "required": "> 0", "pass": bool(bootstrap["ci_low_annualized_arithmetic"] > 0)},
        ]
    )

    verdict = {
        "verdict": "ACADEMIC_SMALL_CAP_MOMENTUM_VS_XSMO",
        "comparison_start": source.index.min().date().isoformat(),
        "comparison_end": source.index.max().date().isoformat(),
        "months": len(source),
        "small_momentum_gross": gross.to_dict(),
        "mtum": mtum.to_dict(),
        "iwm": iwm.to_dict(),
        "small_momentum_cost_25bps_month": cost25.to_dict(),
        "smallest_quintile_gross": smallest.to_dict(),
        "years_beating_mtum_2014_2025": years_beating_mtum,
        "bootstrap_vs_mtum": bootstrap,
        "gates_passed": int(gates["pass"].sum()),
        "gates_total": len(gates),
        "direct_comparison_start": direct_source.index.min().date().isoformat(),
        "direct_comparison_end": direct_source.index.max().date().isoformat(),
        "direct_comparison_months": len(direct_source),
        "direct_small_momentum_gross": direct_gross.to_dict(),
        "xsmo": xsmo.to_dict(),
        "direct_small_momentum_cost_25bps_month": direct_cost25.to_dict(),
        "direct_smallest_quintile_gross": direct_smallest.to_dict(),
        "years_beating_xsmo_2020_2025": years_beating_xsmo,
        "bootstrap_vs_xsmo": bootstrap_xsmo,
        "direct_gates_passed": int(direct_gates["pass"].sum()),
        "direct_gates_total": len(direct_gates),
        "interpretation": (
            "From 2019-07 the academic portfolio beats XSMO on gross CAGR and Sharpe but has a deeper drawdown. "
            "A 25 bps monthly cost stress reverses the CAGR advantage, and the bootstrap confidence interval includes zero. "
            "The result supports further investable research, not live deployment."
        ),
        "live_ready": False,
    }

    output = ROOT / args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(output / "metrics.csv", index=False)
    bucket_metrics.to_csv(output / "bucket_metrics.csv", index=False)
    equity.to_csv(output / "equity.csv", index_label="Date")
    annual.to_csv(output / "annual_returns.csv", index_label="Year")
    subperiod_metrics.to_csv(output / "subperiod_metrics.csv", index=False)
    gates.to_csv(output / "gates.csv", index=False)
    pd.DataFrame([bootstrap]).to_csv(output / "bootstrap_vs_mtum.csv", index=False)
    direct_metrics.to_csv(output / "direct_metrics.csv", index=False)
    direct_equity.to_csv(output / "direct_equity.csv", index_label="Date")
    direct_annual.to_csv(output / "direct_annual_returns.csv", index_label="Year")
    direct_gates.to_csv(output / "direct_gates.csv", index=False)
    pd.DataFrame([bootstrap_xsmo]).to_csv(output / "bootstrap_vs_xsmo.csv", index=False)
    (output / "verdict.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    print(json.dumps(verdict, indent=2))
    print(gates.to_string(index=False))
    print(direct_gates.to_string(index=False))


if __name__ == "__main__":
    main()
