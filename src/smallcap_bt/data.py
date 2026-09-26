from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

from .config import DataConfig

OHLCV = ["Open", "High", "Low", "Close", "Volume"]


def normalize_bars(frame: pd.DataFrame, timezone: str = "America/New_York") -> pd.DataFrame:
    """Return sorted, timezone-aware OHLCV bars with a stable schema."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=OHLCV, index=pd.DatetimeIndex([], name="Datetime"))
    frame = frame.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        # yfinance uses (field, ticker) for a single symbol.
        frame.columns = frame.columns.get_level_values(0)
    aliases = {str(c).lower().replace(" ", "_"): c for c in frame.columns}
    rename = {}
    for expected in OHLCV:
        key = expected.lower()
        if key in aliases:
            rename[aliases[key]] = expected
    frame = frame.rename(columns=rename)
    missing = [c for c in OHLCV if c not in frame.columns]
    if missing:
        raise ValueError(f"Missing OHLCV columns: {missing}")
    frame = frame[OHLCV].apply(pd.to_numeric, errors="coerce")
    frame = frame.dropna(subset=["Open", "High", "Low", "Close"])
    index = pd.DatetimeIndex(frame.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    frame.index = index.tz_convert(timezone)
    frame.index.name = "Datetime"
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    frame["Volume"] = frame["Volume"].fillna(0.0)
    invalid = (frame["Low"] > frame[["Open", "Close", "High"]].min(axis=1)) | (
        frame["High"] < frame[["Open", "Close", "Low"]].max(axis=1)
    )
    if invalid.any():
        raise ValueError(f"Found {int(invalid.sum())} invalid OHLC rows")
    return frame


def regular_session(frame: pd.DataFrame, cfg: DataConfig) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    # End is exclusive: a 16:00 timestamp is an after-hours bar in Yahoo data.
    return frame.between_time(cfg.regular_start, "15:59:59", inclusive="both")


def daily_from_intraday(frame: pd.DataFrame, cfg: DataConfig) -> pd.DataFrame:
    regular = regular_session(frame, cfg)
    if regular.empty:
        return pd.DataFrame(
            columns=["Open", "High", "Low", "Close", "Volume", "BarCount"]
        )
    grouped = regular.groupby(regular.index.date, sort=True)
    daily = grouped.agg(
        Open=("Open", "first"),
        High=("High", "max"),
        Low=("Low", "min"),
        Close=("Close", "last"),
        Volume=("Volume", "sum"),
        BarCount=("Close", "size"),
    )
    daily.index = pd.Index(pd.to_datetime(daily.index), name="Session")
    return daily


def cache_path(ticker: str, cfg: DataConfig) -> Path:
    safe = ticker.upper().replace("/", "-")
    return Path(cfg.cache_dir) / f"{safe}_{cfg.interval}_{cfg.period}.csv"


def save_cache(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index_label="Datetime")


def load_cache(path: Path, timezone: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    # A multi-month local-time CSV can span a DST boundary and therefore contain
    # both -04:00 and -05:00 offsets. Parse through UTC before converting back to
    # the configured exchange timezone.
    frame.index = pd.to_datetime(frame.pop("Datetime"), utc=True)
    frame.index.name = "Datetime"
    return normalize_bars(frame, timezone)


class IntradayProvider(ABC):
    def __init__(self, cfg: DataConfig):
        self.cfg = cfg

    @abstractmethod
    def fetch(self, ticker: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        raise NotImplementedError

    def get(self, ticker: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        path = cache_path(ticker, self.cfg)
        if path.exists() and not self.cfg.refresh and start is None and end is None:
            return load_cache(path, self.cfg.timezone)
        frame = self.fetch(ticker, start=start, end=end)
        if start is None and end is None and not frame.empty:
            save_cache(frame, path)
        return frame


class YFinanceProvider(IntradayProvider):
    def fetch(self, ticker: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        import yfinance as yf

        kwargs = dict(
            tickers=ticker,
            interval=self.cfg.interval,
            auto_adjust=False,
            prepost=self.cfg.prepost,
            progress=False,
            threads=False,
        )
        if start or end:
            kwargs.update(start=start, end=end)
        else:
            kwargs["period"] = self.cfg.period
        frame = yf.download(**kwargs)
        return normalize_bars(frame, self.cfg.timezone)


class AlpacaProvider(IntradayProvider):
    """Alpaca Market Data v2 REST provider; credentials come only from env vars."""

    base_url = "https://data.alpaca.markets/v2/stocks"

    def fetch(self, ticker: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        # Dedicated data-only variable names make research credentials explicit.
        # Legacy Alpaca names remain supported for compatibility.
        key = os.environ.get("APCA_DATA_KEY_ID") or os.environ.get("APCA_API_KEY_ID")
        secret = os.environ.get("APCA_DATA_SECRET_KEY") or os.environ.get("APCA_API_SECRET_KEY")
        if not key or not secret:
            raise RuntimeError(
                "Set APCA_DATA_KEY_ID and APCA_DATA_SECRET_KEY "
                "(or the legacy APCA_API_KEY_ID/APCA_API_SECRET_KEY)"
            )
        if not start or not end:
            raise ValueError("Alpaca requires --start and --end")
        url = f"{self.base_url}/{ticker.upper()}/bars"
        params = {
            "timeframe": "15Min",
            "start": start,
            "end": end,
            "adjustment": "raw",
            "feed": self.cfg.alpaca_feed,
            "sort": "asc",
            "limit": 10_000,
        }
        headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        rows: list[dict] = []
        while True:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            payload = response.json()
            rows.extend(payload.get("bars", []))
            token = payload.get("next_page_token")
            if not token:
                break
            params["page_token"] = token
        frame = pd.DataFrame(rows)
        if frame.empty:
            return normalize_bars(frame, self.cfg.timezone)
        frame = frame.rename(
            columns={"t": "Datetime", "o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"}
        ).set_index("Datetime")
        frame.index = pd.to_datetime(frame.index, utc=True)
        return normalize_bars(frame, self.cfg.timezone)


class PolygonProvider(IntradayProvider):
    """Polygon/Massive aggregate-bars REST provider using POLYGON_API_KEY."""

    base_url = "https://api.polygon.io/v2/aggs/ticker"

    def fetch(self, ticker: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        key = os.environ.get("POLYGON_API_KEY")
        if not key:
            raise RuntimeError("Set POLYGON_API_KEY")
        if not start or not end:
            raise ValueError("Polygon requires --start and --end")
        url = f"{self.base_url}/{ticker.upper()}/range/15/minute/{start}/{end}"
        params = {"adjusted": "false", "sort": "asc", "limit": 50_000, "apiKey": key}
        rows: list[dict] = []
        while url:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            payload = response.json()
            rows.extend(payload.get("results", []))
            url = payload.get("next_url")
            params = {"apiKey": key} if url else {}
        frame = pd.DataFrame(rows)
        if frame.empty:
            return normalize_bars(frame, self.cfg.timezone)
        frame = frame.rename(
            columns={"t": "Datetime", "o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"}
        ).set_index("Datetime")
        frame.index = pd.to_datetime(frame.index, unit="ms", utc=True)
        return normalize_bars(frame, self.cfg.timezone)


def provider_from_config(cfg: DataConfig) -> IntradayProvider:
    providers = {
        "yfinance": YFinanceProvider,
        "alpaca": AlpacaProvider,
        "polygon": PolygonProvider,
    }
    try:
        return providers[cfg.provider.lower()](cfg)
    except KeyError as exc:
        raise ValueError(f"Unknown data provider: {cfg.provider}") from exc


def read_tickers(path: str | Path) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [line.strip().upper() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def download_universe(
    tickers: Iterable[str], provider: IntradayProvider, start: str | None = None, end: str | None = None
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    frames: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    for ticker in tickers:
        try:
            frame = provider.get(ticker, start=start, end=end)
            if frame.empty:
                errors[ticker] = "no bars returned"
            else:
                frames[ticker] = frame
        except Exception as exc:  # keep a broad per-symbol boundary for batch research
            errors[ticker] = f"{type(exc).__name__}: {exc}"
    return frames, errors


def data_quality_summary(ticker: str, frame: pd.DataFrame, cfg: DataConfig) -> dict:
    regular = regular_session(frame, cfg)
    extended = frame.drop(index=regular.index, errors="ignore")
    return {
        "ticker": ticker,
        "first_bar": frame.index.min().isoformat() if not frame.empty else None,
        "last_bar": frame.index.max().isoformat() if not frame.empty else None,
        "bars": int(len(frame)),
        "regular_bars": int(len(regular)),
        "extended_bars": int(len(extended)),
        "zero_volume_bars": int((frame["Volume"] <= 0).sum()) if not frame.empty else 0,
        "zero_volume_extended_bars": int((extended["Volume"] <= 0).sum()) if not extended.empty else 0,
        "duplicate_timestamps": int(frame.index.duplicated().sum()),
        "regular_sessions": int(len(set(regular.index.date))) if not regular.empty else 0,
    }
