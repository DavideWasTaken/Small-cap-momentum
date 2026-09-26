from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from smallcap_bt.config import load_config
from smallcap_bt.data import load_cache, regular_session


ROOT = Path(__file__).resolve().parents[1]
WINDOWS_PATH = ROOT / "outputs" / "historical_5y" / "intraday_windows.csv"
DATA_DIR = ROOT / "data" / "historical_alpaca_sip"
OUTPUT_DIR = ROOT / "outputs" / "historical_5y"


def main() -> None:
    cfg = load_config(ROOT / "configs" / "strategy_v1_frozen.yaml")
    windows = pd.read_csv(WINDOWS_PATH)
    rows = []
    for window in windows.itertuples(index=False):
        path = DATA_DIR / f"{window.window_id}.csv"
        row = {
            "window_id": window.window_id,
            "ticker": window.ticker,
            "file_present": path.exists(),
            "load_ok": False,
            "bars": 0,
            "regular_bars": 0,
            "regular_sessions": 0,
            "duplicate_timestamps": 0,
            "zero_volume_bars": 0,
            "event_sessions_expected": int(window.event_count),
            "event_sessions_present": 0,
            "first_bar": None,
            "last_bar": None,
            "error": "",
        }
        if not path.exists():
            row["error"] = "missing file"
            rows.append(row)
            continue
        try:
            frame = load_cache(path, cfg.data.timezone)
            regular = regular_session(frame, cfg.data)
            session_dates = {value.isoformat() for value in set(regular.index.date)}
            expected = set(str(window.event_sessions).split(";"))
            row.update(
                {
                    "load_ok": True,
                    "bars": len(frame),
                    "regular_bars": len(regular),
                    "regular_sessions": len(session_dates),
                    "duplicate_timestamps": int(frame.index.duplicated().sum()),
                    "zero_volume_bars": int((frame.Volume <= 0).sum()),
                    "event_sessions_present": len(expected & session_dates),
                    "first_bar": frame.index.min().isoformat(),
                    "last_bar": frame.index.max().isoformat(),
                }
            )
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)

    quality = pd.DataFrame(rows)
    quality.to_csv(OUTPUT_DIR / "intraday_window_quality.csv", index=False)
    event_coverage = quality.event_sessions_present.sum() / quality.event_sessions_expected.sum()
    summary = {
        "windows_expected": len(windows),
        "windows_present": int(quality.file_present.sum()),
        "windows_load_ok": int(quality.load_ok.sum()),
        "bars": int(quality.bars.sum()),
        "regular_bars": int(quality.regular_bars.sum()),
        "duplicate_timestamps": int(quality.duplicate_timestamps.sum()),
        "zero_volume_bars": int(quality.zero_volume_bars.sum()),
        "event_sessions_expected": int(quality.event_sessions_expected.sum()),
        "event_sessions_present": int(quality.event_sessions_present.sum()),
        "event_session_coverage": float(event_coverage),
        "failed_windows": int((~quality.load_ok).sum()),
        "order_endpoints_called": False,
    }
    (OUTPUT_DIR / "intraday_quality_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
