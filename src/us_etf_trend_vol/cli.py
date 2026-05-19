from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from us_etf_trend_vol.config import load_runtime_config
from us_etf_trend_vol.data.pipeline import (
    compute_daily_returns,
    persist_data_snapshot,
    universe_to_asset_master,
    validate_prices,
)
from us_etf_trend_vol.data.providers import build_provider
from us_etf_trend_vol.execution.ibkr_paper import IbkrPaperTrader, parse_ibkr_config
from us_etf_trend_vol.execution.orders import (
    latest_prices_from_prices,
    load_current_portfolio,
    target_weights_to_orders,
)
from us_etf_trend_vol.portfolio.construction import construct_target_weights
from us_etf_trend_vol.reporting.report import write_advisory_report, write_backtest_report
from us_etf_trend_vol.signals.engine import generate_monthly_signals
from us_etf_trend_vol.backtest.engine import run_backtest
from us_etf_trend_vol.utils import make_run_id, setup_logger


def _load_market_data(args, strategy):
    asset_master = universe_to_asset_master(strategy["universe"])
    symbols = asset_master[asset_master["active"]]["symbol"].tolist()
    provider = build_provider(args.data_source, getattr(args, "local_csv", None))
    prices = provider.get_daily_prices(symbols, start=args.start, end=args.end)
    prices, quality_report = validate_prices(prices)
    returns = compute_daily_returns(prices)
    return asset_master, prices, returns, quality_report


def cmd_validate_config(args) -> None:
    cfg = load_runtime_config(args.config)
    print(f"OK: {cfg.strategy['name']} version={cfg.strategy['version']} hash={cfg.config_hash}")


def cmd_run_backtest(args) -> None:
    cfg = load_runtime_config(args.config)
    run_id = make_run_id("bt")
    logger = setup_logger(cfg.strategy.get("output", {}).get("logs_dir", "logs"), run_id)
    logger.info("Starting backtest run_id=%s config_hash=%s", run_id, cfg.config_hash)
    asset_master, prices, returns, quality_report = _load_market_data(args, cfg.strategy)
    if not quality_report.empty:
        logger.warning("Data quality issues:\n%s", quality_report.to_string(index=False))
    snapshot = persist_data_snapshot(prices, returns, run_id)
    logger.info("Data snapshot saved: %s", snapshot)
    signals = generate_monthly_signals(prices, returns, cfg.strategy)
    result = run_backtest(prices, returns, signals, asset_master, cfg.strategy, run_id, start=args.start, end=args.end)
    report_path = write_backtest_report(
        run_id=run_id,
        config_hash=cfg.config_hash,
        metrics=result.metrics,
        nav=result.nav,
        trades=result.trades,
        out_dir=cfg.strategy.get("output", {}).get("reports_dir", "reports/backtests"),
    )
    result.nav.to_csv(Path(report_path).with_suffix(".nav.csv"), index=False)
    result.trades.to_csv(Path(report_path).with_suffix(".trades.csv"), index=False)
    logger.info("Report written: %s", report_path)
    print(report_path)


def cmd_suggest(args) -> None:
    cfg = load_runtime_config(args.config)
    run_id = make_run_id("advisory")
    logger = setup_logger(cfg.strategy.get("output", {}).get("logs_dir", "logs"), run_id)
    asset_master, prices, returns, quality_report = _load_market_data(args, cfg.strategy)
    if not quality_report.empty:
        logger.warning("Data quality issues:\n%s", quality_report.to_string(index=False))
    signals = generate_monthly_signals(prices, returns, cfg.strategy)
    latest_signal_date = pd.to_datetime(signals["signal_date"]).max()
    latest_prices = latest_prices_from_prices(prices)
    current_weights = load_current_portfolio(args.portfolio, latest_prices)
    target = construct_target_weights(latest_signal_date, signals, returns, asset_master, cfg.strategy, current_weights=current_weights)
    portfolio_value = float(args.portfolio_value) if args.portfolio_value else 100000.0
    orders = target_weights_to_orders(
        target,
        portfolio_value=portfolio_value,
        latest_prices=latest_prices,
        order_type=cfg.strategy.get("execution", {}).get("order_type", "market"),
        min_trade_notional=float(cfg.strategy.get("execution", {}).get("min_trade_notional", 100.0)),
    )
    orders_path, md_path = write_advisory_report(run_id, orders, target, cfg.strategy.get("output", {}).get("advisory_dir", "reports/advisory"))
    logger.info("Advisory outputs: %s %s", orders_path, md_path)
    print(md_path)


def cmd_ibkr_paper(args) -> None:
    cfg = load_runtime_config(args.config)
    run_id = make_run_id("ibkr_paper")
    logger = setup_logger(cfg.strategy.get("output", {}).get("logs_dir", "logs"), run_id)
    asset_master, prices, returns, quality_report = _load_market_data(args, cfg.strategy)
    if not quality_report.empty:
        logger.warning("Data quality issues:\n%s", quality_report.to_string(index=False))
    signals = generate_monthly_signals(prices, returns, cfg.strategy)
    latest_signal_date = pd.to_datetime(signals["signal_date"]).max()
    latest_prices = latest_prices_from_prices(prices)
    current_weights = load_current_portfolio(args.portfolio, latest_prices)
    target = construct_target_weights(latest_signal_date, signals, returns, asset_master, cfg.strategy, current_weights=current_weights)
    portfolio_value = float(args.portfolio_value) if args.portfolio_value else 100000.0
    orders = target_weights_to_orders(
        target,
        portfolio_value=portfolio_value,
        latest_prices=latest_prices,
        order_type=cfg.strategy.get("execution", {}).get("order_type", "market"),
        min_trade_notional=float(cfg.strategy.get("execution", {}).get("min_trade_notional", 100.0)),
    )
    orders_path, md_path = write_advisory_report(run_id, orders, target, cfg.strategy.get("output", {}).get("advisory_dir", "reports/advisory"))
    logger.info("Generated IBKR paper advisory: %s", md_path)
    if orders.empty:
        print("No proposed orders.")
        return
    trader = IbkrPaperTrader(parse_ibkr_config(cfg.strategy))
    submit = bool(args.submit) and not bool(args.dry_run)
    results = trader.submit_orders(orders, submit=submit, approval_phrase=bool(args.i_understand_paper_trading))
    results_path = Path(orders_path).with_name(f"{run_id}_ibkr_results.csv")
    pd.DataFrame(results).to_csv(results_path, index=False)
    logger.info("IBKR paper results saved: %s", results_path)
    print(results_path)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="us-etf-trend-vol")
    sub = p.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate-config")
    v.add_argument("--config", required=True)
    v.set_defaults(func=cmd_validate_config)

    def add_data_args(sp):
        sp.add_argument("--config", required=True)
        sp.add_argument("--data-source", default="synthetic", choices=["synthetic", "yahoo", "stooq", "local_csv"])
        sp.add_argument("--local-csv", default=None)
        sp.add_argument("--start", default="2010-01-01")
        sp.add_argument("--end", default=None)

    b = sub.add_parser("run-backtest")
    add_data_args(b)
    b.set_defaults(func=cmd_run_backtest)

    s = sub.add_parser("suggest")
    add_data_args(s)
    s.add_argument("--portfolio", default=None)
    s.add_argument("--portfolio-value", default=None)
    s.set_defaults(func=cmd_suggest)

    ib = sub.add_parser("ibkr-paper")
    add_data_args(ib)
    ib.add_argument("--portfolio", default=None)
    ib.add_argument("--portfolio-value", default=None)
    ib.add_argument("--dry-run", action="store_true")
    ib.add_argument("--submit", action="store_true")
    ib.add_argument("--i-understand-paper-trading", action="store_true")
    ib.set_defaults(func=cmd_ibkr_paper)
    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
