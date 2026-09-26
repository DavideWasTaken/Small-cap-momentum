from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import requests


IWM_DOCUMENT_URL = (
    "https://www.blackrock.com/varnish-api/blk-one01-product-data/"
    "product-data/api/v1/get-fund-document"
)
IWM_DOCUMENT_PARAMS = {
    "appSubType": "ISHARES",
    "appType": "PRODUCT_PAGE",
    "component": "fundDownload",
    "locale": "en_US",
    "portfolioId": "239710",
    "targetSite": "us-ishares",
    "userType": "individual",
}


def _spreadsheet_rows(payload: str) -> list[list[str]]:
    rows = re.findall(r"<ss:Row\b.*?</ss:Row>", payload, flags=re.S)
    parsed: list[list[str]] = []
    for row in rows:
        values = []
        for value in re.findall(r"<ss:Data\b[^>]*>(.*?)</ss:Data>", row, flags=re.S):
            values.append(html.unescape(re.sub(r"<[^>]+>", "", value)).strip())
        parsed.append(values)
    return parsed


def parse_iwm_holdings(payload: bytes | str) -> pd.DataFrame:
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    rows = _spreadsheet_rows(text)
    header_index = next(
        (index for index, values in enumerate(rows) if values and values[0] == "Ticker"), None
    )
    if header_index is None:
        raise ValueError("IWM holdings header was not found in the BlackRock export")
    header = rows[header_index]
    records = []
    for values in rows[header_index + 1 :]:
        if values and values[0] == "As Of":
            break
        if len(values) < len(header):
            values = values + [None] * (len(header) - len(values))
        row = dict(zip(header, values[: len(header)]))
        if row.get("Asset Class") != "Equity":
            continue
        ticker = str(row.get("Ticker") or "").strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,7}", ticker) or ticker == "--":
            continue
        if row.get("Currency") != "USD" or row.get("Location") != "United States":
            continue
        row["Ticker"] = ticker
        records.append(row)
    frame = pd.DataFrame(records)
    if frame.empty:
        raise ValueError("No US equity holdings were parsed from the IWM export")
    for column in ["Market Value", "Weight (%)", "Notional Value", "Quantity", "Price", "FX Rate"]:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.drop_duplicates("Ticker", keep="first").reset_index(drop=True)
    return frame


def fetch_iwm_holdings(timeout: int = 90) -> pd.DataFrame:
    response = requests.get(IWM_DOCUMENT_URL, params=IWM_DOCUMENT_PARAMS, timeout=timeout)
    response.raise_for_status()
    return parse_iwm_holdings(response.content)


def yahoo_symbol(ticker: str) -> str:
    # Yahoo represents US class-share punctuation with a dash.
    overrides = {"MOGA": "MOG-A", "CWENA": "CWEN-A", "LENB": "LEN-B"}
    return overrides.get(ticker, ticker.replace(".", "-"))


def _extract_daily_symbol(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()
    if not isinstance(raw.columns, pd.MultiIndex):
        return raw.copy()
    level0 = set(map(str, raw.columns.get_level_values(0)))
    level1 = set(map(str, raw.columns.get_level_values(1)))
    if ticker in level0:
        return raw[ticker].copy()
    if ticker in level1:
        return raw.xs(ticker, axis=1, level=1).copy()
    return pd.DataFrame()


def download_daily_yfinance(
    tickers: Iterable[str],
    period: str = "3mo",
    batch_size: int = 100,
    progress: bool = True,
) -> tuple[pd.DataFrame, list[str]]:
    import yfinance as yf

    symbols = [yahoo_symbol(value) for value in tickers]
    rows: list[pd.DataFrame] = []
    unavailable: list[str] = []
    total_batches = (len(symbols) + batch_size - 1) // batch_size
    for batch_number, offset in enumerate(range(0, len(symbols), batch_size), start=1):
        batch = symbols[offset : offset + batch_size]
        if progress:
            print(f"daily batch {batch_number}/{total_batches}: {len(batch)} ticker", flush=True)
        raw = yf.download(
            tickers=batch,
            period=period,
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            actions=False,
            progress=False,
            threads=True,
            timeout=30,
        )
        for ticker in batch:
            item = _extract_daily_symbol(raw, ticker)
            if item.empty or "Close" not in item or item["Close"].dropna().empty:
                unavailable.append(ticker)
                continue
            item = item.rename(columns={"Adj Close": "AdjClose"})
            for column in ["Open", "High", "Low", "Close", "AdjClose", "Volume"]:
                if column not in item:
                    item[column] = np.nan
            item = item[["Open", "High", "Low", "Close", "AdjClose", "Volume"]]
            item = item.dropna(subset=["Close"]).copy()
            item["Ticker"] = ticker
            item.index = pd.to_datetime(item.index).tz_localize(None)
            item.index.name = "Session"
            rows.append(item.reset_index())
    if not rows:
        return pd.DataFrame(), unavailable
    daily = pd.concat(rows, ignore_index=True)
    daily = daily.drop_duplicates(["Ticker", "Session"], keep="last")
    return daily.sort_values(["Ticker", "Session"]), sorted(set(unavailable))


def screen_daily_spikes(
    daily: pd.DataFrame,
    spike_return_pct: float,
    spike_volume_multiple: float,
    volume_lookback_days: int = 20,
    min_volume_history_days: int = 5,
    min_prior_close: float = 0.50,
    max_prior_close: float = 50.0,
    min_spike_dollar_volume: float = 1_000_000.0,
    min_avg_prior_dollar_volume: float = 0.0,
) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame()
    output = []
    for ticker, group in daily.groupby("Ticker", sort=False):
        group = group.sort_values("Session").copy()
        adjusted = group["AdjClose"].fillna(group["Close"])
        group["PriorClose"] = group["Close"].shift(1)
        group["ReturnPct"] = adjusted / adjusted.shift(1) - 1.0
        group["AvgPriorVolume"] = (
            group["Volume"]
            .shift(1)
            .rolling(volume_lookback_days, min_periods=min_volume_history_days)
            .mean()
        )
        group["VolumeMultiple"] = group["Volume"] / group["AvgPriorVolume"].replace(0, np.nan)
        group["SpikeDollarVolume"] = group["Close"] * group["Volume"]
        group["AvgPriorDollarVolume"] = (
            (group["Close"] * group["Volume"])
            .shift(1)
            .rolling(volume_lookback_days, min_periods=min_volume_history_days)
            .mean()
        )
        matches = group[
            (group["ReturnPct"] >= spike_return_pct)
            & (group["VolumeMultiple"] >= spike_volume_multiple)
            & group["PriorClose"].between(min_prior_close, max_prior_close, inclusive="both")
            & (group["SpikeDollarVolume"] >= min_spike_dollar_volume)
            & (group["AvgPriorDollarVolume"] >= min_avg_prior_dollar_volume)
        ].copy()
        if matches.empty:
            continue
        matches["Ticker"] = ticker
        output.append(matches)
    if not output:
        return pd.DataFrame()
    movers = pd.concat(output, ignore_index=True)
    columns = [
        "Ticker",
        "Session",
        "PriorClose",
        "Open",
        "High",
        "Low",
        "Close",
        "ReturnPct",
        "Volume",
        "VolumeMultiple",
        "SpikeDollarVolume",
        "AvgPriorDollarVolume",
    ]
    return movers[columns].sort_values(["Session", "ReturnPct"], ascending=[False, False])
