from __future__ import annotations

from io import StringIO

import numpy as np
import pandas as pd


MONTHLY_MARKER = "Average Value Weighted Returns -- Monthly"


def parse_french_value_weighted_monthly(
    text: str, marker: str | None = MONTHLY_MARKER
) -> pd.DataFrame:
    """Parse a monthly table in a French-library CSV."""
    lines = text.splitlines()
    if marker is None:
        header_index = next(
            (
                index
                for index, line in enumerate(lines[:-1])
                if "," in line
                and len(lines[index + 1].split(",", 1)[0].strip()) == 6
                and lines[index + 1].split(",", 1)[0].strip().isdigit()
            ),
            -1,
        )
    else:
        try:
            marker_index = next(index for index, line in enumerate(lines) if marker in line)
        except StopIteration as exc:
            raise ValueError("Requested monthly table marker was not found") from exc
        header_index = marker_index + 1
    if header_index < 0 or header_index >= len(lines) or "," not in lines[header_index]:
        raise ValueError("Monthly table header was not found")
    data_lines: list[str] = []
    for line in lines[header_index + 1 :]:
        first = line.split(",", 1)[0].strip()
        if len(first) != 6 or not first.isdigit():
            break
        data_lines.append(line)
    if not data_lines:
        raise ValueError("Monthly table contains no observations")

    frame = pd.read_csv(StringIO("\n".join([lines[header_index], *data_lines])))
    frame = frame.rename(columns={frame.columns[0]: "yyyymm"})
    frame["Date"] = pd.PeriodIndex(frame.pop("yyyymm").astype(str), freq="M").to_timestamp("M")
    frame = frame.set_index("Date")
    frame = frame.apply(pd.to_numeric, errors="coerce")
    frame = frame.mask(frame <= -99.0) / 100.0
    frame.index.name = "Date"
    return frame


def month_end_returns(adjusted_close: pd.DataFrame | pd.Series) -> pd.DataFrame:
    prices = adjusted_close.to_frame() if isinstance(adjusted_close, pd.Series) else adjusted_close.copy()
    prices.index = pd.to_datetime(prices.index).tz_localize(None)
    prices = prices.sort_index()
    monthly_prices = prices.resample("ME").last()
    returns = monthly_prices.pct_change(fill_method=None)
    returns.index.name = "Date"
    return returns


def performance_metrics(returns: pd.Series, risk_free: pd.Series | None = None) -> dict:
    values = pd.to_numeric(returns, errors="coerce").dropna()
    if values.empty:
        raise ValueError("Cannot calculate performance metrics for an empty return series")
    if (values <= -1).any():
        raise ValueError("Monthly returns must be greater than -100%")

    wealth = (1.0 + values).cumprod()
    drawdown = wealth / wealth.cummax() - 1.0
    months = len(values)
    annualized_volatility = float(values.std(ddof=1) * np.sqrt(12))
    if risk_free is None:
        excess = values
    else:
        aligned_rf = pd.to_numeric(risk_free, errors="coerce").reindex(values.index)
        if aligned_rf.isna().any():
            raise ValueError("Risk-free series does not cover every return month")
        excess = values - aligned_rf
    excess_volatility = float(excess.std(ddof=1) * np.sqrt(12))
    sharpe = float(excess.mean() * 12 / excess_volatility) if excess_volatility else np.nan
    cagr = float(wealth.iloc[-1] ** (12.0 / months) - 1.0)
    max_drawdown = float(drawdown.min())
    return {
        "months": int(months),
        "total_return": float(wealth.iloc[-1] - 1.0),
        "cagr": cagr,
        "annualized_volatility": annualized_volatility,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "calmar": float(cagr / abs(max_drawdown)) if max_drawdown < 0 else np.nan,
        "worst_month": float(values.min()),
        "best_month": float(values.max()),
        "positive_month_rate": float((values > 0).mean()),
    }


def circular_block_bootstrap_mean_difference(
    difference: pd.Series,
    *,
    samples: int = 20_000,
    block_months: int = 12,
    seed: int = 20260712,
) -> dict:
    values = pd.to_numeric(difference, errors="coerce").dropna().to_numpy(dtype=float)
    if len(values) < block_months:
        raise ValueError("Return difference is shorter than the requested bootstrap block")
    rng = np.random.default_rng(seed)
    block_count = int(np.ceil(len(values) / block_months))
    starts = np.arange(len(values))
    means = np.empty(samples, dtype=float)
    offsets = np.arange(block_months)
    for sample in range(samples):
        chosen_starts = rng.choice(starts, size=block_count, replace=True)
        indices = ((chosen_starts[:, None] + offsets) % len(values)).ravel()[: len(values)]
        means[sample] = values[indices].mean()
    low, high = np.quantile(means, [0.025, 0.975])
    return {
        "samples": int(samples),
        "block_months": int(block_months),
        "mean_monthly_difference": float(values.mean()),
        "annualized_arithmetic_difference": float(values.mean() * 12),
        "ci_low_monthly": float(low),
        "ci_high_monthly": float(high),
        "ci_low_annualized_arithmetic": float(low * 12),
        "ci_high_annualized_arithmetic": float(high * 12),
    }


def annual_returns(monthly_returns: pd.DataFrame) -> pd.DataFrame:
    compounded = (1.0 + monthly_returns).groupby(monthly_returns.index.year).prod() - 1.0
    compounded.index.name = "Year"
    return compounded
