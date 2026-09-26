from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, time

import numpy as np
import pandas as pd

from .config import DataConfig, StrategyConfig
from .data import daily_from_intraday, regular_session


@dataclass(frozen=True)
class SpikeEvent:
    ticker: str
    session: date
    prior_close: float
    close: float
    high: float
    return_pct: float
    volume: float
    volume_multiple: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SetupSignal:
    ticker: str
    spike_session: date
    trigger_session: date
    spike_high: float
    spike_return_pct: float
    spike_volume_multiple: float
    consolidation_low: float
    consolidation_high: float
    consolidation_range_pct: float
    resistance_level: float
    resistance_tests: int
    resistance_touch_times: tuple[pd.Timestamp, ...]
    resistance_source: str
    breakout_time: pd.Timestamp
    pullback_start: pd.Timestamp
    pullback_end: pd.Timestamp
    pullback_low: float
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    entry_price_raw: float

    def to_dict(self) -> dict:
        result = asdict(self)
        for key in ("breakout_time", "pullback_start", "pullback_end", "signal_time", "entry_time"):
            result[key] = result[key].isoformat()
        result["spike_session"] = self.spike_session.isoformat()
        result["trigger_session"] = self.trigger_session.isoformat()
        result["resistance_touch_times"] = [x.isoformat() for x in self.resistance_touch_times]
        return result


def _parse_time(value: str) -> time:
    return pd.Timestamp(value).time()


def detect_spikes(
    ticker: str, frame: pd.DataFrame, data_cfg: DataConfig, cfg: StrategyConfig
) -> list[SpikeEvent]:
    daily = daily_from_intraday(frame, data_cfg).copy()
    if daily.empty:
        return []
    daily["PriorClose"] = daily["Close"].shift(1)
    daily["ReturnPct"] = daily["Close"] / daily["PriorClose"] - 1.0
    daily["AvgPriorVolume"] = (
        daily["Volume"].shift(1).rolling(cfg.volume_lookback_days, min_periods=cfg.min_volume_history_days).mean()
    )
    daily["VolumeMultiple"] = daily["Volume"] / daily["AvgPriorVolume"].replace(0, np.nan)
    matches = daily[
        (daily["ReturnPct"] >= cfg.spike_return_pct)
        & (daily["VolumeMultiple"] >= cfg.spike_volume_multiple)
    ]
    events = []
    for idx, row in matches.iterrows():
        events.append(
            SpikeEvent(
                ticker=ticker,
                session=idx.date(),
                prior_close=float(row.PriorClose),
                close=float(row.Close),
                high=float(row.High),
                return_pct=float(row.ReturnPct),
                volume=float(row.Volume),
                volume_multiple=float(row.VolumeMultiple),
            )
        )
    return events


def _swing_highs(frame: pd.DataFrame, window: int) -> pd.Series:
    highs = frame["High"].astype(float)
    width = window * 2 + 1
    local_max = highs.rolling(width, center=True, min_periods=1).max()
    mask = highs >= local_max
    return highs[mask]


def find_resistance(
    consolidation: pd.DataFrame, cfg: StrategyConfig
) -> tuple[float, tuple[pd.Timestamp, ...]] | None:
    if consolidation.empty:
        return None
    swings = _swing_highs(consolidation, cfg.swing_window)
    if len(swings) < cfg.resistance_tests:
        return None
    floor = float(consolidation["High"].quantile(cfg.resistance_top_quantile))
    swings = swings[swings >= floor]
    candidates: list[tuple[float, pd.Series]] = []
    for seed in swings.values:
        denom = max(abs(float(seed)), 1e-9)
        touches = swings[(swings - float(seed)).abs() / denom <= cfg.resistance_tolerance_pct]
        if len(touches) >= cfg.resistance_tests:
            level = float(touches.median())
            candidates.append((level, touches))
    if not candidates:
        return None
    # A resistance is the highest repeatedly tested cluster, not the densest
    # cluster in the middle of a sideways range.
    level, touches = max(candidates, key=lambda item: (item[0], len(item[1])))
    unique_times = tuple(pd.DatetimeIndex(touches.index).sort_values().unique())
    return level, unique_times


def _session_positions(frame: pd.DataFrame, data_cfg: DataConfig) -> list[date]:
    regular = regular_session(frame, data_cfg)
    return sorted(set(regular.index.date))


def build_setup(
    ticker: str,
    frame: pd.DataFrame,
    trigger_session: date,
    data_cfg: DataConfig,
    cfg: StrategyConfig,
) -> tuple[SpikeEvent, float, tuple[pd.Timestamp, ...], str, pd.DataFrame] | None:
    sessions = _session_positions(frame, data_cfg)
    if trigger_session not in sessions:
        return None
    trigger_pos = sessions.index(trigger_session)
    spikes = {event.session: event for event in detect_spikes(ticker, frame, data_cfg, cfg)}
    eligible: list[tuple[int, SpikeEvent]] = []
    for spike_date, event in spikes.items():
        if spike_date not in sessions:
            continue
        age = trigger_pos - sessions.index(spike_date)
        if cfg.spike_lookback_min_sessions <= age <= cfg.spike_lookback_max_sessions:
            eligible.append((age, event))
    for _, spike in sorted(eligible, key=lambda pair: pair[0]):
        spike_cutoff = pd.Timestamp.combine(spike.session, _parse_time(data_cfg.regular_end)).tz_localize(
            data_cfg.timezone
        )
        consolidation = frame[(frame.index >= spike_cutoff) & (frame.index.date < trigger_session)]
        if not cfg.include_extended_setup:
            consolidation = regular_session(consolidation, data_cfg)
        if consolidation.empty:
            continue
        low = float(consolidation["Low"].min())
        high = float(consolidation["High"].max())
        midpoint = max((high + low) / 2.0, 1e-9)
        range_pct = (high - low) / midpoint
        if range_pct > cfg.consolidation_max_range_pct:
            continue
        if low / spike.high < cfg.consolidation_min_low_vs_spike_high:
            continue
        override = cfg.level_overrides.get(ticker, {}).get(trigger_session.isoformat())
        if override is not None:
            level = float(override)
            swing_highs = _swing_highs(consolidation, cfg.swing_window)
            touches = swing_highs[(swing_highs - level).abs() / level <= cfg.resistance_tolerance_pct]
            touch_times = tuple(pd.DatetimeIndex(touches.index).sort_values().unique())
            source = "override"
        else:
            found = find_resistance(consolidation, cfg)
            if found is None:
                continue
            level, touch_times = found
            source = "automatic"
        if len(touch_times) < cfg.resistance_tests:
            continue
        return spike, level, touch_times, source, consolidation
    return None


def detect_trigger(
    ticker: str,
    frame: pd.DataFrame,
    trigger_session: date,
    data_cfg: DataConfig,
    cfg: StrategyConfig,
) -> SetupSignal | None:
    built = build_setup(ticker, frame, trigger_session, data_cfg, cfg)
    if built is None:
        return None
    spike, level, touch_times, source, consolidation = built
    day = frame[frame.index.date == trigger_session]
    if day.empty:
        return None
    start, end = _parse_time(cfg.trigger_start), _parse_time(cfg.trigger_end)
    candidates = day[(day.index.time >= start) & (day.index.time <= end)]
    if not cfg.include_extended_breakout:
        candidates = regular_session(candidates, data_cfg)
    breakout_threshold = level * (1.0 + cfg.breakout_buffer_pct)
    breakout_mask = (
        candidates["Close"] > breakout_threshold
        if cfg.breakout_on_close
        else candidates["High"] > breakout_threshold
    )
    if not breakout_mask.any():
        return None
    breakout_time = breakout_mask[breakout_mask].index[0]
    post_breakout = day[day.index > breakout_time]
    if cfg.pullback_regular_session_only:
        post_breakout = regular_session(post_breakout, data_cfg)
    post_breakout = post_breakout[post_breakout.index.time <= end]
    if post_breakout.empty:
        return None
    approaches = post_breakout[
        post_breakout["Low"] <= level * (1.0 + cfg.pullback_max_above_level_pct)
    ]
    if approaches.empty:
        return None
    pullback_start = approaches.index[0]
    start_loc = post_breakout.index.get_loc(pullback_start)
    hold = post_breakout.iloc[start_loc : start_loc + cfg.hold_bars]
    if len(hold) < cfg.hold_bars:
        return None
    hold_floor = level * (1.0 - cfg.hold_tolerance_pct)
    if not (hold["Low"] >= hold_floor).all():
        return None
    # The pullback may briefly close under the exact line while remaining inside
    # the configured tolerance; the confirmation bar must reclaim it.
    if cfg.require_hold_close_above_level and float(hold.iloc[-1]["Close"]) < level:
        return None
    pullback_end = hold.index[-1]
    regular = regular_session(day, data_cfg)
    eligible_entries = regular[(regular.index > pullback_end) & (regular["Volume"] > 0)]
    if eligible_entries.empty:
        return None
    entry_time = eligible_entries.index[0]
    entry_price = float(eligible_entries.iloc[0]["Open"])
    if entry_price < hold_floor:
        return None
    if entry_price > level * (1.0 + cfg.max_entry_extension_pct):
        return None
    low = float(consolidation["Low"].min())
    high = float(consolidation["High"].max())
    midpoint = max((high + low) / 2.0, 1e-9)
    return SetupSignal(
        ticker=ticker,
        spike_session=spike.session,
        trigger_session=trigger_session,
        spike_high=spike.high,
        spike_return_pct=spike.return_pct,
        spike_volume_multiple=spike.volume_multiple,
        consolidation_low=low,
        consolidation_high=high,
        consolidation_range_pct=(high - low) / midpoint,
        resistance_level=level,
        resistance_tests=len(touch_times),
        resistance_touch_times=touch_times,
        resistance_source=source,
        breakout_time=breakout_time,
        pullback_start=pullback_start,
        pullback_end=pullback_end,
        pullback_low=float(hold["Low"].min()),
        signal_time=pullback_end,
        entry_time=entry_time,
        entry_price_raw=entry_price,
    )


def scan_signals(
    ticker: str, frame: pd.DataFrame, data_cfg: DataConfig, cfg: StrategyConfig
) -> list[SetupSignal]:
    signals: list[SetupSignal] = []
    used_spikes: set[date] = set()
    for session in _session_positions(frame, data_cfg):
        signal = detect_trigger(ticker, frame, session, data_cfg, cfg)
        if signal is None:
            continue
        if cfg.one_trade_per_setup and signal.spike_session in used_spikes:
            continue
        signals.append(signal)
        used_spikes.add(signal.spike_session)
    return signals


def screen_recent_movers(
    frames: dict[str, pd.DataFrame], data_cfg: DataConfig, cfg: StrategyConfig, recent_sessions: int = 5
) -> pd.DataFrame:
    rows = []
    for ticker, frame in frames.items():
        daily = daily_from_intraday(frame, data_cfg)
        if daily.empty:
            continue
        recent_dates = set(x.date() for x in daily.index[-recent_sessions:])
        for event in detect_spikes(ticker, frame, data_cfg, cfg):
            if event.session in recent_dates:
                rows.append(event.to_dict())
    if not rows:
        return pd.DataFrame(
            columns=["ticker", "session", "prior_close", "close", "high", "return_pct", "volume", "volume_multiple"]
        )
    return pd.DataFrame(rows).sort_values(["session", "return_pct"], ascending=[False, False])


def audit_candidates(
    frames: dict[str, pd.DataFrame], data_cfg: DataConfig, cfg: StrategyConfig
) -> pd.DataFrame:
    """Create a compact stage audit without changing signal-generation rules."""
    rows = []
    for ticker, frame in frames.items():
        sessions = _session_positions(frame, data_cfg)
        spikes = detect_spikes(ticker, frame, data_cfg, cfg)
        signals = scan_signals(ticker, frame, data_cfg, cfg)
        setup_sessions: set[date] = set()
        for spike in spikes:
            if spike.session not in sessions:
                continue
            spike_pos = sessions.index(spike.session)
            for age in range(cfg.spike_lookback_min_sessions, cfg.spike_lookback_max_sessions + 1):
                candidate_pos = spike_pos + age
                if candidate_pos >= len(sessions):
                    continue
                candidate = sessions[candidate_pos]
                if build_setup(ticker, frame, candidate, data_cfg, cfg) is not None:
                    setup_sessions.add(candidate)
        if signals:
            status = "signal"
        elif not spikes:
            status = "daily_spike_not_confirmed_from_intraday"
        elif not setup_sessions:
            status = "no_valid_consolidation_or_resistance"
        else:
            status = "setup_without_valid_breakout_hold_entry"
        rows.append(
            {
                "ticker": ticker,
                "status": status,
                "intraday_spike_count": len(spikes),
                "spike_sessions": ";".join(event.session.isoformat() for event in spikes),
                "valid_setup_session_count": len(setup_sessions),
                "valid_setup_sessions": ";".join(value.isoformat() for value in sorted(setup_sessions)),
                "signal_count": len(signals),
                "signal_sessions": ";".join(signal.trigger_session.isoformat() for signal in signals),
            }
        )
    return pd.DataFrame(rows).sort_values(["status", "ticker"])
