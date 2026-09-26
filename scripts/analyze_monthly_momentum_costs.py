from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from smallcap_bt.monthly_momentum import performance_metrics


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "monthly_momentum"


def net_metrics(
    gross_returns: pd.Series,
    risk_free: pd.Series,
    annual_drag: float,
) -> dict[str, float]:
    return performance_metrics(gross_returns - annual_drag / 12.0, risk_free)


def break_even_cost_bps_per_side(
    gross_returns: pd.Series,
    risk_free: pd.Series,
    benchmark_cagr: float,
    annual_one_way_turnover: float,
) -> float:
    low, high = 0.0, 500.0
    for _ in range(80):
        midpoint = (low + high) / 2.0
        annual_drag = 2.0 * annual_one_way_turnover * midpoint / 10_000.0
        cagr = net_metrics(gross_returns, risk_free, annual_drag)["cagr"]
        if cagr > benchmark_cagr:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2.0


def main() -> None:
    config = yaml.safe_load(
        (ROOT / "configs" / "monthly_momentum_academic.yaml").read_text(encoding="utf-8")
    )
    cost_config = config["implementation_costs"]
    source = pd.read_csv(OUTPUT / "source_returns.csv", parse_dates=["Date"]).set_index("Date")
    direct = source.loc["2019-07-31":]
    direct_metrics = pd.read_csv(OUTPUT / "direct_metrics.csv").set_index("series")
    gross_returns = direct.ff_2x3_small_high
    risk_free = direct.rf
    gross_cagr = float(direct_metrics.loc["Small momentum gross", "cagr"])
    xsmo_cagr = float(direct_metrics.loc["XSMO", "cagr"])
    gross_cagr_edge = gross_cagr - xsmo_cagr

    turnover_scenarios = {
        "XSMO reported fiscal-year turnover": cost_config["annual_one_way_turnover"]["xsmo_reported"],
        "Moderate monthly momentum proxy": cost_config["annual_one_way_turnover"]["moderate_proxy"],
        "Academic monthly momentum proxy": cost_config["annual_one_way_turnover"]["academic_monthly_proxy"],
        "High-turnover stress": cost_config["annual_one_way_turnover"]["high_stress"],
    }
    break_even_rows = []
    grid_rows = []
    for label, turnover in turnover_scenarios.items():
        break_even_rows.append(
            {
                "turnover_scenario": label,
                "annual_one_way_turnover": turnover,
                "break_even_all_in_cost_bps_per_side": break_even_cost_bps_per_side(
                    gross_returns,
                    risk_free,
                    xsmo_cagr,
                    turnover,
                ),
            }
        )
        for cost_bps in cost_config["all_in_cost_bps_per_side"]:
            annual_drag = 2.0 * turnover * cost_bps / 10_000.0
            metrics = net_metrics(gross_returns, risk_free, annual_drag)
            grid_rows.append(
                {
                    "turnover_scenario": label,
                    "annual_one_way_turnover": turnover,
                    "all_in_cost_bps_per_side": cost_bps,
                    "annual_trading_drag": annual_drag,
                    "net_cagr": metrics["cagr"],
                    "net_sharpe": metrics["sharpe"],
                    "net_max_drawdown": metrics["max_drawdown"],
                    "cagr_gap_vs_xsmo": metrics["cagr"] - xsmo_cagr,
                    "beats_xsmo": bool(metrics["cagr"] > xsmo_cagr),
                }
            )

    # Optimistic retail implementation: 120 names, one order per name each
    # monthly rebalance. Ticket costs are minimum-only lower bounds and exclude
    # venue, regulatory, spread, slippage, market impact, data and tax costs.
    capital_rows = []
    academic_turnover = turnover_scenarios["Academic monthly momentum proxy"]
    market_cost_bps_per_side = cost_config["retail_market_cost_bps_per_side"]
    market_drag = 2.0 * academic_turnover * market_cost_bps_per_side / 10_000.0
    for capital in cost_config["capital_usd"]:
        for orders_per_rebalance in cost_config["orders_per_month"]:
            annual_orders = orders_per_rebalance * 12
            for pricing_plan, minimum_per_order in [
                ("IBKR Pro Tiered", cost_config["ibkr_minimum_per_order_usd"]["tiered"]),
                ("IBKR Pro Fixed", cost_config["ibkr_minimum_per_order_usd"]["fixed"]),
            ]:
                annual_ticket_cost = annual_orders * minimum_per_order
                ticket_drag = annual_ticket_cost / capital
                annual_drag = market_drag + ticket_drag
                metrics = net_metrics(gross_returns, risk_free, annual_drag)
                capital_rows.append(
                    {
                        "capital_usd": capital,
                        "orders_per_month": orders_per_rebalance,
                        "annual_orders": annual_orders,
                        "pricing_plan": pricing_plan,
                        "minimum_commission_per_order_usd": minimum_per_order,
                        "annual_minimum_commissions_usd": annual_ticket_cost,
                        "annual_minimum_commission_drag": ticket_drag,
                        "assumed_annual_one_way_turnover": academic_turnover,
                        "assumed_market_cost_bps_per_side": market_cost_bps_per_side,
                        "annual_market_cost_drag": market_drag,
                        "annual_total_drag_before_tax": annual_drag,
                        "net_cagr": metrics["cagr"],
                        "cagr_gap_vs_xsmo": metrics["cagr"] - xsmo_cagr,
                        "beats_xsmo": bool(metrics["cagr"] > xsmo_cagr),
                    }
                )

    break_even = pd.DataFrame(break_even_rows)
    grid = pd.DataFrame(grid_rows)
    capital = pd.DataFrame(capital_rows)
    academic_break_even = float(
        break_even.loc[
            break_even.turnover_scenario.eq("Academic monthly momentum proxy"),
            "break_even_all_in_cost_bps_per_side",
        ].iloc[0]
    )
    tiered_120 = capital[
        capital.pricing_plan.eq("IBKR Pro Tiered") & capital.orders_per_month.eq(120)
    ]
    positive_capitals = tiered_120.loc[tiered_120.beats_xsmo, "capital_usd"]
    first_positive_capital = int(positive_capitals.min()) if not positive_capitals.empty else None

    verdict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "PREFER_XSMO_UNTIL_REAL_TURNOVER_AND_FILLS_PROVE_OTHERWISE",
        "comparison_period": "2019-07-31 to 2026-05-31",
        "gross_cagr_academic": gross_cagr,
        "cagr_xsmo_net_fund_path": xsmo_cagr,
        "gross_cagr_edge": gross_cagr_edge,
        "xsmo_total_expense_ratio": 0.0036,
        "xsmo_reported_portfolio_turnover": 1.15,
        "academic_monthly_momentum_turnover_proxy": academic_turnover,
        "break_even_cost_bps_per_side_at_academic_turnover": academic_break_even,
        "historical_academic_cost_reference": {
            "estimated_monthly_cost": 0.004839,
            "source_period": "1963-07 to 2013-12",
            "scope": "Fama-French UMD long-short factor; not a direct current-cost estimate for this long-only portfolio",
        },
        "ibkr_ticket_cost_assumption": {
            "tiered_minimum_usd": 0.35,
            "fixed_minimum_usd": 1.00,
            "orders_per_month_scenarios": [60, 120],
            "fractional_order_warning": "IBKR states fractional trades are charged the greater of 1% of trade value or USD 0.01.",
        },
        "optimistic_scenario": {
            "turnover": academic_turnover,
            "market_cost_bps_per_side": market_cost_bps_per_side,
            "orders_per_month": 120,
            "pricing": "IBKR Pro Tiered minimum only",
            "first_tested_capital_that_still_beats_xsmo": first_positive_capital,
        },
        "tax_caveat": (
            "Italian-resident realized financial gains can be subject to 26% substitute tax, but the incremental tax drag "
            "cannot be quantified without tax regime, lots, losses and distributions. Higher self-directed turnover generally "
            "accelerates realization relative to holding one ETF."
        ),
        "decision": (
            "Do not implement the academic portfolio live. XSMO already packages the exposure and its observed return includes "
            "fund expenses and internal turnover. The academic portfolio has only a 2.82 percentage-point gross CAGR budget; "
            "at a 305% turnover proxy it must keep all-in execution below the calculated break-even level, before tax, while "
            "the available academic cost evidence is worse. A constituent-level backtest with actual turnover and paper fills "
            "is required to overturn this decision."
        ),
        "sources": {
            "ibkr_commissions": "https://www.interactivebrokers.com/en/pricing/commissions-stocks.php",
            "xsmo_prospectus": "https://www.sec.gov/Archives/edgar/data/1209466/000119312525190429/d56632d497k.htm",
            "academic_turnover_proxy": "https://www.tandfonline.com/doi/abs/10.1080/0015198X.2024.2317323",
            "academic_trading_costs": "https://www.nber.org/papers/w20721.pdf",
            "italian_tax": "https://infoprecompilata.agenziaentrate.gov.it/portale/semplificata-mod-plusvalenze-natura-finanziaria",
        },
        "live_ready": False,
    }

    break_even.to_csv(OUTPUT / "cost_break_even.csv", index=False)
    grid.to_csv(OUTPUT / "turnover_cost_grid.csv", index=False)
    capital.to_csv(OUTPUT / "capital_cost_scenarios.csv", index=False)
    (OUTPUT / "implementation_cost_verdict.json").write_text(
        json.dumps(verdict, indent=2), encoding="utf-8"
    )
    print(json.dumps(verdict, indent=2))
    print(break_even.to_string(index=False))
    print(tiered_120.to_string(index=False))


if __name__ == "__main__":
    main()
