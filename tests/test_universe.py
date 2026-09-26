from __future__ import annotations

import pandas as pd

from smallcap_bt.universe import parse_iwm_holdings, screen_daily_spikes


def test_parse_iwm_spreadsheet_filters_to_us_equities():
    payload = b"""<?xml version='1.0'?>
    <ss:Workbook xmlns:ss='urn:schemas-microsoft-com:office:spreadsheet'><ss:Table>
    <ss:Row><ss:Cell><ss:Data ss:Type='String'>Ticker</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>Name</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>Sector</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>Asset Class</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>Market Value</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>Weight (%)</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>Notional Value</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>Quantity</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>Price</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>Location</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>Exchange</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>Currency</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>FX Rate</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>Accrual Date</ss:Data></ss:Cell></ss:Row>
    <ss:Row><ss:Cell><ss:Data ss:Type='String'>TEST</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>Test Inc</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>Tech</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>Equity</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='Number'>100</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='Number'>1</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='Number'>100</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='Number'>10</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='Number'>10</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>United States</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>NASDAQ</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>USD</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='Number'>1</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>--</ss:Data></ss:Cell></ss:Row>
    <ss:Row><ss:Cell><ss:Data ss:Type='String'>USD</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>Cash</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>Cash</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type='String'>Cash</ss:Data></ss:Cell></ss:Row>
    <ss:Row><ss:Cell><ss:Data ss:Type='String'>As Of</ss:Data></ss:Cell></ss:Row>
    </ss:Table></ss:Workbook>"""
    result = parse_iwm_holdings(payload)
    assert result["Ticker"].tolist() == ["TEST"]
    assert result.iloc[0]["Price"] == 10


def test_daily_screen_finds_only_liquid_spike():
    sessions = pd.date_range("2026-01-02", periods=8, freq="B")
    rows = []
    for ticker, final_volume in [("PASS", 1_000_000), ("FAIL", 100)]:
        for index, session in enumerate(sessions):
            close = 2.0 if index == len(sessions) - 1 else 1.0
            volume = final_volume if index == len(sessions) - 1 else 1000
            rows.append(
                {
                    "Ticker": ticker,
                    "Session": session,
                    "Open": 1.0,
                    "High": close,
                    "Low": 0.9,
                    "Close": close,
                    "AdjClose": close,
                    "Volume": volume,
                }
            )
    result = screen_daily_spikes(
        pd.DataFrame(rows),
        spike_return_pct=0.5,
        spike_volume_multiple=5,
        min_volume_history_days=5,
        min_spike_dollar_volume=1_000_000,
    )
    assert result["Ticker"].tolist() == ["PASS"]


def test_daily_screen_can_require_prior_dollar_liquidity():
    sessions = pd.date_range("2026-01-02", periods=8, freq="B")
    rows = []
    for index, session in enumerate(sessions):
        final = index == len(sessions) - 1
        close = 2.0 if final else 1.0
        rows.append(
            {
                "Ticker": "THIN",
                "Session": session,
                "Open": 1.0,
                "High": close,
                "Low": 0.9,
                "Close": close,
                "AdjClose": close,
                "Volume": 1_000_000 if final else 1_000,
            }
        )
    result = screen_daily_spikes(
        pd.DataFrame(rows),
        spike_return_pct=0.5,
        spike_volume_multiple=5,
        min_volume_history_days=5,
        min_spike_dollar_volume=1_000_000,
        min_avg_prior_dollar_volume=500_000,
    )
    assert result.empty
