from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from smallcap_bt.config import load_config
from smallcap_bt.data import provider_from_config, save_cache


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download bounded historical 15m windows from a market-data endpoint."
    )
    parser.add_argument("--config", default="configs/strategy_v1_frozen.yaml")
    parser.add_argument("--windows", default="outputs/historical_5y/intraday_windows.csv")
    parser.add_argument("--data-dir", default="data/historical_alpaca_sip")
    parser.add_argument("--status", default="outputs/historical_5y/intraday_download_status.csv")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    provider = provider_from_config(cfg.data)
    windows = pd.read_csv(args.windows)
    if args.limit:
        windows = windows.head(args.limit)
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    status_path = Path(args.status)
    existing_rows = []
    if status_path.exists() and not args.refresh:
        existing_rows = pd.read_csv(status_path).to_dict(orient="records")
    status_by_id = {row["window_id"]: row for row in existing_rows}

    for number, row in enumerate(windows.itertuples(index=False), start=1):
        destination = data_dir / f"{row.window_id}.csv"
        if destination.exists() and not args.refresh:
            print(f"[{number}/{len(windows)}] cached {row.window_id}", flush=True)
            status_by_id[row.window_id] = {
                "window_id": row.window_id,
                "ticker": row.ticker,
                "status": "cached",
                "bars": len(pd.read_csv(destination, usecols=["Datetime"])),
                "error": "",
            }
            continue
        print(f"[{number}/{len(windows)}] fetch {row.window_id}", flush=True)
        try:
            frame = provider.fetch(row.ticker, start=row.start, end=row.end_exclusive)
            if frame.empty:
                raise RuntimeError("no bars returned")
            save_cache(frame, destination)
            status_by_id[row.window_id] = {
                "window_id": row.window_id,
                "ticker": row.ticker,
                "status": "downloaded",
                "bars": len(frame),
                "error": "",
            }
        except Exception as exc:
            status_by_id[row.window_id] = {
                "window_id": row.window_id,
                "ticker": row.ticker,
                "status": "error",
                "bars": 0,
                "error": f"{type(exc).__name__}: {exc}",
            }
        status_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(status_by_id.values()).to_csv(status_path, index=False)

    status = pd.DataFrame(status_by_id.values())
    summary = {
        "windows_requested": len(windows),
        "windows_with_data": int(status.status.isin(["cached", "downloaded"]).sum()),
        "errors": int((status.status == "error").sum()),
        "bars": int(status.bars.sum()),
        "provider": cfg.data.provider,
        "feed": cfg.data.alpaca_feed,
        "order_endpoints_called": False,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
