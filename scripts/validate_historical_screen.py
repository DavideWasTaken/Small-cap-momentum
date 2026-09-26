from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "outputs" / "historical_5y"


def main() -> None:
    daily = pd.read_csv(DATA / "daily_history.csv", parse_dates=["Session"])
    events = pd.read_csv(DATA / "daily_spike_events.csv", parse_dates=["Session"])
    windows = pd.read_csv(DATA / "intraday_windows.csv")
    complete_event_keys = {
        (row.ticker, session)
        for row in windows.itertuples(index=False)
        for session in str(row.event_sessions).split(";")
    }
    checks = []

    def add(name: str, observed: int | float, expected: str, passed: bool, severity: str) -> None:
        checks.append(
            {
                "check": name,
                "observed": observed,
                "expected": expected,
                "status": "PASS" if passed else "FAIL",
                "severity": severity,
            }
        )

    add(
        "daily ticker/session duplicates",
        int(daily.duplicated(["Ticker", "Session"]).sum()),
        "0",
        not daily.duplicated(["Ticker", "Session"]).any(),
        "critical",
    )
    add("daily missing Close", int(daily.Close.isna().sum()), "0", not daily.Close.isna().any(), "critical")
    add("daily missing Volume", int(daily.Volume.isna().sum()), "0", not daily.Volume.isna().any(), "high")
    add(
        "event ticker/session duplicates",
        int(events.duplicated(["Ticker", "Session"]).sum()),
        "0",
        not events.duplicated(["Ticker", "Session"]).any(),
        "critical",
    )
    rules = {
        "event return below 50%": events.ReturnPct < 0.50,
        "event volume multiple below 5x": events.VolumeMultiple < 5.0,
        "event prior price outside 0.50-50": ~events.PriorClose.between(0.50, 50.0),
        "event dollar volume below $1m": events.SpikeDollarVolume < 1_000_000,
        "event prior average dollar volume below $500k": events.AvgPriorDollarVolume < 500_000,
    }
    for name, failed in rules.items():
        add(name, int(failed.sum()), "0", not failed.any(), "critical")
    add(
        "event tickers missing from daily history",
        int((~events.Ticker.isin(daily.Ticker.unique())).sum()),
        "0",
        events.Ticker.isin(daily.Ticker.unique()).all(),
        "critical",
    )
    add(
        "complete event keys represented in windows",
        len(complete_event_keys),
        str(int(windows.event_count.sum())),
        len(complete_event_keys) == int(windows.event_count.sum()),
        "critical",
    )
    overlaps = 0
    for _, group in windows.sort_values(["ticker", "start"]).groupby("ticker"):
        previous_end = None
        for row in group.itertuples(index=False):
            start = pd.Timestamp(row.start)
            end = pd.Timestamp(row.end_exclusive)
            if previous_end is not None and start < previous_end:
                overlaps += 1
            previous_end = end
    add("overlapping merged windows per ticker", overlaps, "0", overlaps == 0, "high")
    add(
        "windows ending after 2026-07-11",
        int((pd.to_datetime(windows.end_exclusive) > pd.Timestamp("2026-07-11")).sum()),
        "0",
        not (pd.to_datetime(windows.end_exclusive) > pd.Timestamp("2026-07-11")).any(),
        "high",
    )

    result = pd.DataFrame(checks)
    result.to_csv(DATA / "data_quality_checks.csv", index=False)
    summary = {
        "daily_rows": len(daily),
        "daily_tickers": int(daily.Ticker.nunique()),
        "spike_events_total": len(events),
        "complete_events_in_manifest": len(complete_event_keys),
        "windows": len(windows),
        "checks": len(result),
        "failed_checks": int((result.status == "FAIL").sum()),
        "known_high_risk_caveat": "current holdings create survivorship bias",
    }
    (DATA / "validation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(result.to_string(index=False))


if __name__ == "__main__":
    main()
