from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from smallcap_bt.config import load_config
from smallcap_bt.universe import download_daily_yfinance, screen_daily_spikes


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare multi-year daily spike events before requesting intraday data."
    )
    parser.add_argument("--period", default="5y")
    parser.add_argument("--config", default="configs/iwm_regular_only.yaml")
    parser.add_argument(
        "--holdings", default="outputs/iwm_automated/iwm_holdings_current.csv"
    )
    parser.add_argument("--output-dir", default="outputs/historical_5y")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--reuse-daily", action="store_true")
    parser.add_argument("--min-avg-prior-dollar-volume", type=float, default=500_000.0)
    args = parser.parse_args()

    cfg = load_config(args.config)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    holdings = pd.read_csv(args.holdings)
    tickers = holdings["Ticker"].dropna().astype(str).drop_duplicates().tolist()
    daily_path = output / "daily_history.csv"
    unavailable_path = output / "unavailable_tickers.csv"
    if args.reuse_daily and daily_path.exists():
        daily = pd.read_csv(daily_path, parse_dates=["Session"])
        unavailable = (
            pd.read_csv(unavailable_path)["Ticker"].dropna().astype(str).tolist()
            if unavailable_path.exists()
            else []
        )
    else:
        daily, unavailable = download_daily_yfinance(
            tickers, period=args.period, batch_size=args.batch_size, progress=True
        )
    unfiltered_events = screen_daily_spikes(
        daily,
        spike_return_pct=cfg.strategy.spike_return_pct,
        spike_volume_multiple=cfg.strategy.spike_volume_multiple,
        volume_lookback_days=cfg.strategy.volume_lookback_days,
        min_volume_history_days=cfg.strategy.min_volume_history_days,
        min_prior_close=0.50,
        max_prior_close=50.0,
        min_spike_dollar_volume=1_000_000.0,
    )
    thresholds = [0, 100_000, 250_000, 500_000, 1_000_000, 2_000_000]
    sensitivity = pd.DataFrame(
        [
            {
                "min_avg_prior_dollar_volume": threshold,
                "events": int((unfiltered_events.AvgPriorDollarVolume >= threshold).sum()),
                "tickers": int(
                    unfiltered_events.loc[
                        unfiltered_events.AvgPriorDollarVolume >= threshold, "Ticker"
                    ].nunique()
                ),
            }
            for threshold in thresholds
        ]
    )
    sensitivity.to_csv(output / "liquidity_filter_sensitivity.csv", index=False)
    events = unfiltered_events[
        unfiltered_events.AvgPriorDollarVolume >= args.min_avg_prior_dollar_volume
    ].copy()
    daily.to_csv(output / "daily_history.csv", index=False)
    events.to_csv(output / "daily_spike_events.csv", index=False)
    pd.DataFrame({"Ticker": unavailable}).to_csv(output / "unavailable_tickers.csv", index=False)
    if events.empty:
        by_year = pd.DataFrame(columns=["year", "events", "tickers"])
    else:
        events["Year"] = pd.to_datetime(events["Session"]).dt.year
        by_year = (
            events.groupby("Year")
            .agg(events=("Ticker", "size"), tickers=("Ticker", "nunique"))
            .reset_index()
            .rename(columns={"Year": "year"})
        )
    by_year.to_csv(output / "events_by_year.csv", index=False)
    summary = {
        "period": args.period,
        "holdings_current": len(tickers),
        "daily_tickers_loaded": int(daily.Ticker.nunique()) if not daily.empty else 0,
        "daily_rows": len(daily),
        "unavailable_tickers": len(unavailable),
        "qualified_spike_events": len(events),
        "qualified_spike_events_before_prior_liquidity_filter": len(unfiltered_events),
        "min_avg_prior_dollar_volume": args.min_avg_prior_dollar_volume,
        "unique_event_tickers": int(events.Ticker.nunique()) if not events.empty else 0,
        "first_session": str(daily.Session.min()) if not daily.empty else None,
        "last_session": str(daily.Session.max()) if not daily.empty else None,
        "survivorship_bias": "current IWM holdings; not point-in-time",
        "next_required_input": "15-minute historical bars around each event",
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
