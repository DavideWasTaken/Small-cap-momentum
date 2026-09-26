from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .backtest import equity_and_metrics, run_backtest, signals_frame, trades_frame
from .config import BacktestConfig, load_config
from .data import (
    data_quality_summary,
    daily_from_intraday,
    download_universe,
    provider_from_config,
    read_tickers,
)
from .plotting import plot_equity_curve, plot_trade, plot_variant_returns
from .robustness import run_readiness_analysis
from .strategy import audit_candidates, detect_spikes, screen_recent_movers
from .universe import download_daily_yfinance, fetch_iwm_holdings, screen_daily_spikes


def _ensure_output(cfg: BacktestConfig) -> Path:
    output = Path(cfg.output.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    return output


def _load_frames(args, cfg: BacktestConfig, tickers: list[str]):
    if getattr(args, "refresh", False):
        cfg.data.refresh = True
    provider = provider_from_config(cfg.data)
    return download_universe(tickers, provider, start=args.start, end=args.end)


def _write_common(output: Path, frames, errors, cfg: BacktestConfig) -> pd.DataFrame:
    quality = pd.DataFrame(
        [data_quality_summary(ticker, frame, cfg.data) for ticker, frame in frames.items()]
    )
    quality.to_csv(output / "data_quality.csv", index=False)
    (output / "run_metadata.json").write_text(
        json.dumps(
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "config": cfg.to_dict(),
                "tickers_loaded": sorted(frames),
                "download_errors": errors,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    if errors:
        pd.DataFrame([{"ticker": k, "error": v} for k, v in errors.items()]).to_csv(
            output / "download_errors.csv", index=False
        )
    return quality


def command_validate(args) -> int:
    cfg = load_config(args.config)
    output = _ensure_output(cfg)
    frames, errors = _load_frames(args, cfg, [args.ticker.upper()])
    quality = _write_common(output, frames, errors, cfg)
    if args.ticker.upper() not in frames:
        print(json.dumps({"status": "blocked", "errors": errors}, indent=2))
        return 2
    ticker = args.ticker.upper()
    frame = frames[ticker]
    daily = daily_from_intraday(frame, cfg.data)
    daily.to_csv(output / f"{ticker}_daily.csv")
    spikes = pd.DataFrame([x.to_dict() for x in detect_spikes(ticker, frame, cfg.data, cfg.strategy)])
    spikes.to_csv(output / "spikes.csv", index=False)
    signals, trades = run_backtest(frames, cfg)
    audit = audit_candidates(frames, cfg.data, cfg.strategy)
    audit.to_csv(output / "candidate_audit.csv", index=False)
    signals_df, trades_df = signals_frame(signals), trades_frame(trades)
    signals_df.to_csv(output / "signals.csv", index=False)
    trades_df.to_csv(output / "trades.csv", index=False)
    metrics, equity = equity_and_metrics(trades, cfg.risk)
    metrics.to_csv(output / "metrics.csv", index=False)
    equity.to_csv(output / "equity.csv", index=False)
    if cfg.output.save_trade_charts:
        for trade in trades:
            filename = (
                f"{trade.ticker}_{trade.trigger_session}_{trade.variant}_{trade.resistance_source}.png"
            )
            plot_trade(trade, frame, cfg, output / "trades" / filename)
    plot_equity_curve(equity, output / "equity_curve.png")
    plot_variant_returns(metrics, output / "expectancy_by_variant.png")
    summary = {
        "status": "ok",
        "ticker": ticker,
        "quality": quality.to_dict(orient="records"),
        "spikes": spikes.to_dict(orient="records"),
        "signals": signals_df.to_dict(orient="records"),
        "metrics": metrics.to_dict(orient="records"),
        "output": str(output.resolve()),
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0


def command_screen(args) -> int:
    cfg = load_config(args.config)
    output = _ensure_output(cfg)
    tickers = read_tickers(args.tickers_file)
    if args.limit:
        tickers = tickers[: args.limit]
    frames, errors = _load_frames(args, cfg, tickers)
    _write_common(output, frames, errors, cfg)
    movers = screen_recent_movers(frames, cfg.data, cfg.strategy, args.recent_sessions)
    movers.to_csv(output / "recent_movers.csv", index=False)
    print(
        json.dumps(
            {
                "status": "ok",
                "loaded": len(frames),
                "errors": len(errors),
                "recent_movers": movers.to_dict(orient="records"),
                "output": str(output.resolve()),
            },
            indent=2,
            default=str,
        )
    )
    return 0


def command_backtest(args) -> int:
    cfg = load_config(args.config)
    output = _ensure_output(cfg)
    tickers = read_tickers(args.tickers_file)
    if args.limit:
        tickers = tickers[: args.limit]
    frames, errors = _load_frames(args, cfg, tickers)
    quality = _write_common(output, frames, errors, cfg)
    movers = screen_recent_movers(frames, cfg.data, cfg.strategy, args.recent_sessions)
    movers.to_csv(output / "recent_movers.csv", index=False)
    signals, trades = run_backtest(frames, cfg)
    signals_df, trades_df = signals_frame(signals), trades_frame(trades)
    signals_df.to_csv(output / "signals.csv", index=False)
    trades_df.to_csv(output / "trades.csv", index=False)
    metrics, equity = equity_and_metrics(trades, cfg.risk)
    metrics.to_csv(output / "metrics.csv", index=False)
    equity.to_csv(output / "equity.csv", index=False)
    if cfg.output.save_trade_charts:
        for trade in trades:
            filename = f"{trade.ticker}_{trade.trigger_session}_{trade.variant}.png"
            plot_trade(trade, frames[trade.ticker], cfg, output / "trades" / filename)
    plot_equity_curve(equity, output / "equity_curve.png")
    plot_variant_returns(metrics, output / "expectancy_by_variant.png")
    print(
        json.dumps(
            {
                "status": "ok",
                "loaded_tickers": len(frames),
                "download_errors": len(errors),
                "quality_rows": len(quality),
                "signals": len(signals),
                "trades": len(trades),
                "metrics": metrics.to_dict(orient="records"),
                "output": str(output.resolve()),
            },
            indent=2,
            default=str,
        )
    )
    return 0


def command_broad_backtest(args) -> int:
    cfg = load_config(args.config)
    output = _ensure_output(cfg)
    holdings = fetch_iwm_holdings()
    holdings.to_csv(output / "iwm_holdings_current.csv", index=False)
    tickers = holdings["Ticker"].tolist()
    daily, unavailable_daily = download_daily_yfinance(
        tickers, period=args.daily_period, batch_size=args.batch_size, progress=True
    )
    daily.to_csv(output / "daily_history.csv", index=False)
    movers = screen_daily_spikes(
        daily,
        spike_return_pct=cfg.strategy.spike_return_pct,
        spike_volume_multiple=cfg.strategy.spike_volume_multiple,
        volume_lookback_days=cfg.strategy.volume_lookback_days,
        min_volume_history_days=cfg.strategy.min_volume_history_days,
        min_prior_close=args.min_prior_close,
        max_prior_close=args.max_prior_close,
        min_spike_dollar_volume=args.min_spike_dollar_volume,
    )
    movers.to_csv(output / "daily_mover_events.csv", index=False)
    candidates = list(dict.fromkeys(movers.get("Ticker", pd.Series(dtype=str)).tolist()))
    for ticker in args.extra_ticker:
        ticker = ticker.upper()
        if ticker not in candidates:
            candidates.append(ticker)
    if args.max_candidates:
        candidates = candidates[: args.max_candidates]
    (output / "intraday_candidates.txt").write_text("\n".join(candidates) + "\n", encoding="utf-8")
    provider = provider_from_config(cfg.data)
    frames, intraday_errors = download_universe(candidates, provider, start=args.start, end=args.end)
    quality = _write_common(output, frames, intraday_errors, cfg)
    signals, trades = run_backtest(frames, cfg)
    audit = audit_candidates(frames, cfg.data, cfg.strategy)
    audit.to_csv(output / "candidate_audit.csv", index=False)
    signals_df, trades_df = signals_frame(signals), trades_frame(trades)
    signals_df.to_csv(output / "signals.csv", index=False)
    trades_df.to_csv(output / "trades.csv", index=False)
    metrics, equity = equity_and_metrics(trades, cfg.risk)
    metrics.to_csv(output / "metrics.csv", index=False)
    equity.to_csv(output / "equity.csv", index=False)
    if cfg.output.save_trade_charts:
        for trade in trades:
            filename = f"{trade.ticker}_{trade.trigger_session}_{trade.variant}.png"
            plot_trade(trade, frames[trade.ticker], cfg, output / "trades" / filename)
    plot_equity_curve(equity, output / "equity_curve.png")
    plot_variant_returns(metrics, output / "expectancy_by_variant.png")
    automation = {
        "iwm_holdings": len(holdings),
        "daily_tickers_loaded": int(daily["Ticker"].nunique()) if not daily.empty else 0,
        "daily_unavailable": len(unavailable_daily),
        "daily_spike_events": len(movers),
        "intraday_candidates": len(candidates),
        "intraday_loaded": len(frames),
        "intraday_errors": len(intraday_errors),
        "automatic_signals": len(signals),
        "candidates_with_signal": int((audit["status"] == "signal").sum()) if not audit.empty else 0,
        "trades": len(trades),
    }
    (output / "automation_summary.json").write_text(
        json.dumps(automation, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "ok",
                **automation,
                "quality_rows": len(quality),
                "metrics": metrics.to_dict(orient="records"),
                "output": str(output.resolve()),
            },
            indent=2,
            default=str,
        )
    )
    return 0


def command_robustness(args) -> int:
    cfg = load_config(args.config)
    tickers = read_tickers(args.tickers_file)
    frames, errors = _load_frames(args, cfg, tickers)
    results = run_readiness_analysis(frames, cfg, args.output_dir)
    scorecard = results["readiness_scorecard"]
    summary = {
        "status": "ok",
        "tickers_requested": len(tickers),
        "tickers_loaded": len(frames),
        "download_errors": errors,
        "blocking_failures": int(
            ((scorecard["blocking_for_live"]) & (scorecard["status"] == "FAIL")).sum()
        ),
        "output": str(Path(args.output_dir).resolve()),
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Small-cap momentum continuation backtest")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default="configs/default.yaml")
    common.add_argument("--start", default=None, help="ISO date/time; required by Alpaca/Polygon")
    common.add_argument("--end", default=None, help="ISO date/time; required by Alpaca/Polygon")
    common.add_argument("--refresh", action="store_true", help="Ignore the local CSV cache")

    validate = sub.add_parser("validate", parents=[common], help="Run one ticker and emit charts")
    validate.add_argument("--ticker", default="CLRO")
    validate.set_defaults(func=command_validate)

    screen = sub.add_parser("screen", parents=[common], help="Screen recent movers")
    screen.add_argument("--tickers-file", default="configs/tickers.txt")
    screen.add_argument("--recent-sessions", type=int, default=5)
    screen.add_argument("--limit", type=int, default=None)
    screen.set_defaults(func=command_screen)

    backtest = sub.add_parser("backtest", parents=[common], help="Screen and backtest a universe")
    backtest.add_argument("--tickers-file", default="configs/tickers.txt")
    backtest.add_argument("--recent-sessions", type=int, default=5)
    backtest.add_argument("--limit", type=int, default=None)
    backtest.set_defaults(func=command_backtest)

    broad = sub.add_parser(
        "broad-backtest", parents=[common], help="Daily-screen IWM, then backtest only intraday candidates"
    )
    broad.add_argument("--daily-period", default="3mo")
    broad.add_argument("--batch-size", type=int, default=100)
    broad.add_argument("--min-prior-close", type=float, default=0.50)
    broad.add_argument("--max-prior-close", type=float, default=50.0)
    broad.add_argument("--min-spike-dollar-volume", type=float, default=1_000_000.0)
    broad.add_argument("--max-candidates", type=int, default=None)
    broad.add_argument("--extra-ticker", action="append", default=["CLRO"])
    broad.set_defaults(func=command_broad_backtest)

    robustness = sub.add_parser(
        "robustness", parents=[common], help="Stress-test automation and execution readiness"
    )
    robustness.add_argument(
        "--tickers-file", default="outputs/iwm_automated/intraday_candidates.txt"
    )
    robustness.add_argument("--output-dir", default="outputs/automation_readiness")
    robustness.set_defaults(func=command_robustness)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
