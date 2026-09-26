from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class DataConfig:
    provider: str = "yfinance"
    interval: str = "15m"
    period: str = "60d"
    prepost: bool = True
    timezone: str = "America/New_York"
    regular_start: str = "09:30"
    regular_end: str = "16:00"
    cache_dir: str = "data/raw"
    refresh: bool = False
    alpaca_feed: str = "iex"


@dataclass
class StrategyConfig:
    spike_return_pct: float = 0.50
    spike_volume_multiple: float = 5.0
    volume_lookback_days: int = 20
    min_volume_history_days: int = 5
    spike_lookback_min_sessions: int = 1
    spike_lookback_max_sessions: int = 5
    consolidation_max_range_pct: float = 0.50
    consolidation_min_low_vs_spike_high: float = 0.55
    resistance_tests: int = 3
    resistance_tolerance_pct: float = 0.05
    resistance_top_quantile: float = 0.65
    swing_window: int = 1
    include_extended_setup: bool = True
    breakout_buffer_pct: float = 0.0
    breakout_on_close: bool = True
    include_extended_breakout: bool = True
    trigger_start: str = "04:00"
    trigger_end: str = "11:30"
    pullback_regular_session_only: bool = True
    pullback_max_above_level_pct: float = 0.20
    hold_tolerance_pct: float = 0.04
    hold_bars: int = 2
    require_hold_close_above_level: bool = True
    entry_execution: str = "next_bar_open"
    max_entry_extension_pct: float = 0.20
    one_trade_per_setup: bool = True
    level_overrides: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass
class RiskConfig:
    stop_mode: str = "pullback"
    stop_buffer_pct: float = 0.005
    fixed_stop_pct: float = 0.10
    target_pcts: list[float] = field(default_factory=lambda: [0.20, 0.25])
    trailing_stop_pct: float = 0.15
    exit_variants: list[str] = field(
        default_factory=lambda: ["target_20", "target_25", "trailing", "eod"]
    )
    intrabar_priority: str = "stop"
    slippage_bps_per_side: float = 10.0
    commission_bps_per_side: float = 2.0
    initial_capital: float = 100_000.0
    risk_per_trade: float = 0.01
    max_position_pct: float = 0.25


@dataclass
class OutputConfig:
    output_dir: str = "outputs"
    save_trade_charts: bool = True
    chart_bars_before: int = 60
    chart_bars_after: int = 24


@dataclass
class BacktestConfig:
    data: DataConfig = field(default_factory=DataConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _merge_dataclass(cls: type, values: dict[str, Any] | None):
    values = values or {}
    valid = cls.__dataclass_fields__
    unknown = sorted(set(values) - set(valid))
    if unknown:
        raise ValueError(f"Unknown {cls.__name__} fields: {unknown}")
    return cls(**values)


def load_config(path: str | Path) -> BacktestConfig:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    allowed = {"data", "strategy", "risk", "output"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(f"Unknown top-level config fields: {unknown}")
    return BacktestConfig(
        data=_merge_dataclass(DataConfig, raw.get("data")),
        strategy=_merge_dataclass(StrategyConfig, raw.get("strategy")),
        risk=_merge_dataclass(RiskConfig, raw.get("risk")),
        output=_merge_dataclass(OutputConfig, raw.get("output")),
    )
