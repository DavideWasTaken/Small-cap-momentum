from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def merge_windows(events: pd.DataFrame, days_before: int, days_after: int) -> pd.DataFrame:
    rows = []
    for ticker, group in events.groupby("Ticker"):
        sessions = sorted(pd.to_datetime(group["Session"]).dt.normalize().unique())
        raw = [
            {
                "start": pd.Timestamp(session) - pd.Timedelta(days=days_before),
                "end": pd.Timestamp(session) + pd.Timedelta(days=days_after),
                "events": [pd.Timestamp(session)],
            }
            for session in sessions
        ]
        merged: list[dict] = []
        for item in raw:
            if merged and item["start"] <= merged[-1]["end"]:
                merged[-1]["end"] = max(merged[-1]["end"], item["end"])
                merged[-1]["events"].extend(item["events"])
            else:
                merged.append(item)
        for number, item in enumerate(merged, start=1):
            rows.append(
                {
                    "window_id": f"{ticker}_{number:03d}_{item['start']:%Y%m%d}_{item['end']:%Y%m%d}",
                    "ticker": ticker,
                    "start": item["start"].date().isoformat(),
                    # Alpaca's end is exclusive; add one day to include this date.
                    "end_exclusive": (item["end"] + pd.Timedelta(days=1)).date().isoformat(),
                    "event_count": len(item["events"]),
                    "event_sessions": ";".join(x.date().isoformat() for x in item["events"]),
                }
            )
    return pd.DataFrame(rows).sort_values(["start", "ticker"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create bounded 15m download windows around spikes.")
    parser.add_argument("--events", default="outputs/historical_5y/daily_spike_events.csv")
    parser.add_argument("--output", default="outputs/historical_5y/intraday_windows.csv")
    parser.add_argument("--days-before", type=int, default=35)
    parser.add_argument("--days-after", type=int, default=10)
    parser.add_argument(
        "--asof",
        default=None,
        help="Exclude events whose full post-event window is not complete by this ISO date.",
    )
    args = parser.parse_args()
    events = pd.read_csv(args.events)
    excluded_incomplete = 0
    if args.asof:
        cutoff = pd.Timestamp(args.asof).normalize() - pd.Timedelta(days=args.days_after)
        complete = pd.to_datetime(events["Session"]).dt.normalize() <= cutoff
        excluded_incomplete = int((~complete).sum())
        events = events[complete].copy()
    windows = merge_windows(events, args.days_before, args.days_after)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    windows.to_csv(path, index=False)
    print(
        {
            "events": len(events),
            "tickers": int(events.Ticker.nunique()),
            "merged_windows": len(windows),
            "excluded_incomplete_events": excluded_incomplete,
            "first_start": windows.start.min(),
            "last_end_exclusive": windows.end_exclusive.max(),
        }
    )


if __name__ == "__main__":
    main()
