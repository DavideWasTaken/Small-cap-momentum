from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from io import TextIOWrapper
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import requests
import yfinance as yf
import yaml

from smallcap_bt.monthly_momentum import month_end_returns, parse_french_value_weighted_monthly


ROOT = Path(__file__).resolve().parents[1]
FF6_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/6_Portfolios_ME_Prior_12_2_CSV.zip"
FF25_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/25_Portfolios_ME_Prior_12_2_CSV.zip"
FACTORS_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_CSV.zip"


def download(url: str, destination: Path, refresh: bool) -> None:
    if destination.exists() and not refresh:
        return
    response = requests.get(url, timeout=90)
    response.raise_for_status()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(response.content)


def read_first_csv(zip_path: Path) -> str:
    with ZipFile(zip_path) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"Expected one CSV in {zip_path}, found {len(names)}")
        with archive.open(names[0]) as handle:
            return TextIOWrapper(handle, encoding="utf-8", errors="replace").read()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def adjusted_close(raw: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    if raw.empty:
        raise RuntimeError("ETF download returned no rows")
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Adj Close"].copy()
    else:
        prices = raw[["Adj Close"]].copy()
        prices.columns = tickers
    missing = [ticker for ticker in tickers if ticker not in prices or prices[ticker].dropna().empty]
    if missing:
        raise RuntimeError(f"ETF adjusted-close data missing for: {missing}")
    return prices[tickers]


def main() -> None:
    parser = argparse.ArgumentParser(description="Download academic monthly momentum and ETF benchmark data.")
    parser.add_argument("--config", default="configs/monthly_momentum_academic.yaml")
    parser.add_argument("--data-dir", default="data/monthly_momentum")
    parser.add_argument("--output-dir", default="outputs/monthly_momentum")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    config = yaml.safe_load((ROOT / args.config).read_text(encoding="utf-8"))
    comparison = config["comparison"]
    start = pd.Timestamp(comparison["start_month"])
    end = pd.Timestamp(comparison["end_month"])
    tickers = [
        comparison["momentum_etf"],
        comparison["small_cap_etf"],
        comparison["direct_small_cap_momentum_etf"],
    ]

    data_dir = ROOT / args.data_dir
    output_dir = ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    archives = {
        "ff6": (FF6_URL, data_dir / "6_Portfolios_ME_Prior_12_2_CSV.zip"),
        "ff25": (FF25_URL, data_dir / "25_Portfolios_ME_Prior_12_2_CSV.zip"),
        "factors": (FACTORS_URL, data_dir / "F-F_Research_Data_Factors_CSV.zip"),
    }
    for url, path in archives.values():
        download(url, path, args.refresh)

    six = parse_french_value_weighted_monthly(read_first_csv(archives["ff6"][1]))
    twenty_five = parse_french_value_weighted_monthly(read_first_csv(archives["ff25"][1]))
    factors = parse_french_value_weighted_monthly(
        read_first_csv(archives["factors"][1]), marker=None
    )

    raw_etfs = yf.download(
        tickers=tickers,
        start=(start - pd.offsets.MonthEnd(1) - pd.Timedelta(days=7)).strftime("%Y-%m-%d"),
        end=(end + pd.Timedelta(days=3)).strftime("%Y-%m-%d"),
        auto_adjust=False,
        actions=False,
        progress=False,
        threads=False,
        timeout=60,
    )
    etf_prices = adjusted_close(raw_etfs, tickers)
    etf_returns = month_end_returns(etf_prices)
    etf_prices.to_csv(data_dir / "etf_adjusted_daily.csv", index_label="Date")

    source = pd.concat(
        [
            six["SMALL LoPRIOR"].rename("ff_2x3_small_low"),
            six["ME1 PRIOR2"].rename("ff_2x3_small_neutral"),
            six["SMALL HiPRIOR"].rename("ff_2x3_small_high"),
            twenty_five["SMALL HiPRIOR"].rename("ff_5x5_smallest_high"),
            factors["RF"].rename("rf"),
            etf_returns[tickers[0]].rename(tickers[0].lower()),
            etf_returns[tickers[1]].rename(tickers[1].lower()),
            etf_returns[tickers[2]].rename(tickers[2].lower()),
        ],
        axis=1,
        sort=True,
    ).loc[start:end]
    complete = source.dropna()
    if complete.empty:
        raise RuntimeError("No complete common monthly observations were found")
    if complete.index.min() != start or complete.index.max() != end:
        raise RuntimeError(
            f"Common coverage is {complete.index.min().date()} to {complete.index.max().date()}, "
            f"expected {start.date()} to {end.date()}"
        )
    if len(complete) != len(pd.period_range(start, end, freq="M")):
        raise RuntimeError("Common monthly series has missing months")

    complete.to_csv(output_dir / "source_returns.csv", index_label="Date")
    quality = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "first_month": complete.index.min().date().isoformat(),
        "last_month": complete.index.max().date().isoformat(),
        "months": len(complete),
        "columns": list(complete.columns),
        "missing_values": int(complete.isna().sum().sum()),
        "duplicate_months": int(complete.index.duplicated().sum()),
        "academic_source": "Kenneth French Data Library, CRSP 202605 release",
        "benchmark_source": "Yahoo Finance adjusted close",
        "xsmo_official_product_source": "https://www.invesco.com/us/en/financial-products/etfs/invesco-sp-smallcap-momentum-etf.html",
        "xsmo_official_methodology_source": "https://www.spglobal.com/spdji/en/documents/methodologies/methodology-sp-momentum-indices.pdf",
        "xsmo_mandate_change_source": "https://www.nyse.com/publicdocs/nyse/markets/nyse-arca/rule-interpretations/2019/NYSE%20Arca%20Equities%20RB-19-095.pdf",
        "xsmo_total_expense_ratio": 0.0036,
        "direct_benchmark_valid_from": comparison["direct_benchmark_start_month"],
        "direct_benchmark_reason": (
            "XSMO began tracking the current S&P SmallCap 600 Momentum Index on 2019-06-21; "
            "the primary direct comparison starts with the first full following month."
        ),
        "portfolio_construction": "monthly value-weighted size x prior-return portfolios; prior return t-12 to t-2",
        "known_limitations": [
            "Academic portfolio returns are gross of implementation costs.",
            "The French small portfolio is not identical to the S&P SmallCap 600 or Russell 2000 universe.",
            "ETF adjusted-close history is a secondary market-data source and is reconciled only at aggregate level.",
            "XSMO ticker history before 2019-06-21 reflects different underlying indices and is excluded from the primary direct comparison.",
        ],
        "archives": {
            key: {"url": url, "sha256": sha256(path)} for key, (url, path) in archives.items()
        },
        "order_endpoints_called": False,
    }
    (output_dir / "data_quality.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
    print(json.dumps(quality, indent=2))


if __name__ == "__main__":
    main()
