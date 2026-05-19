from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from us_etf_trend_vol.portfolio.construction import construct_target_weights
from us_etf_trend_vol.risk.metrics import calculate_performance_metrics


@dataclass
class BacktestResult:
    run_id: str
    nav: pd.DataFrame
    trades: pd.DataFrame
    weights: pd.DataFrame
    metrics: dict[str, float | str]


def _cost_bps_for_symbol(symbol: str, asset_master: pd.DataFrame, cost_model: dict) -> float:
    meta = asset_master.set_index("symbol")
    tier = meta.loc[symbol, "liquidity_tier"] if symbol in meta.index else "medium"
    spread = cost_model.get("spread_cost_bps", {}).get(tier, cost_model.get("spread_cost_bps", {}).get("medium", 3))
    slip = cost_model.get("slippage_bps", {}).get(tier, cost_model.get("slippage_bps", {}).get("medium", 5))
    mult = float(cost_model.get("stress_test_multiplier", 1.0))
    return (spread + slip) * mult


def _daily_expense_drag(weights: pd.Series, asset_master: pd.DataFrame) -> float:
    meta = asset_master.set_index("symbol")
    total = 0.0
    for sym, w in weights.items():
        if sym in meta.index:
            total += float(w) * float(meta.loc[sym, "expense_ratio"])
    return total / 252.0


def run_backtest(
    prices: pd.DataFrame,
    returns: pd.DataFrame,
    signals: pd.DataFrame,
    asset_master: pd.DataFrame,
    strategy: dict,
    run_id: str,
    start: str | None = None,
    end: str | None = None,
) -> BacktestResult:
    returns = returns.copy()
    returns["date"] = pd.to_datetime(returns["date"])
    if start:
        returns = returns[returns["date"] >= pd.to_datetime(start)]
    if end:
        returns = returns[returns["date"] <= pd.to_datetime(end)]
    returns = returns.sort_values("date")

    all_symbols = list(asset_master["symbol"])
    wide = returns.pivot(index="date", columns="symbol", values="adjusted_return").reindex(columns=all_symbols).fillna(0.0)
    signal_dates = sorted(pd.to_datetime(signals["signal_date"].unique()))
    signal_dates = [d for d in signal_dates if wide.index.min() <= d <= wide.index.max()]
    signal_set = set(signal_dates)

    nav_rows = []
    trade_rows = []
    weight_rows = []
    nav = float(strategy.get("initial_capital", 100000))
    weights = pd.Series(0.0, index=all_symbols, dtype=float)
    cash = strategy["cash_asset"]
    if cash in weights.index:
        weights[cash] = 1.0

    pending_target: pd.Series | None = None
    pending_signal_date: pd.Timestamp | None = None
    cost_model = strategy.get("cost_model", {})

    dates = list(wide.index)
    for i, dt in enumerate(dates):
        # Execute target on the first trading day after signal date.
        if pending_target is not None and pending_signal_date is not None and dt > pending_signal_date:
            trade_weight = pending_target - weights
            turnover = float(trade_weight.abs().sum())
            cost = 0.0
            for sym, tw in trade_weight.items():
                if abs(tw) <= 1e-12:
                    continue
                bps = _cost_bps_for_symbol(sym, asset_master, cost_model)
                notional = abs(tw) * nav
                this_cost = notional * bps / 10000.0 + float(cost_model.get("commission_per_trade", 0.0))
                cost += this_cost
                trade_rows.append(
                    {
                        "date": dt.date(),
                        "signal_date": pending_signal_date.date(),
                        "symbol": sym,
                        "trade_weight": float(tw),
                        "notional": float(tw * nav),
                        "cost": float(this_cost),
                    }
                )
            nav -= cost
            weights = pending_target.copy()
            weight_rows.append(
                pd.DataFrame(
                    {
                        "date": dt.date(),
                        "symbol": weights.index,
                        "weight": weights.values,
                        "turnover": turnover,
                    }
                )
            )
            pending_target = None
            pending_signal_date = None

        day_ret_by_symbol = wide.loc[dt]
        port_ret = float((weights * day_ret_by_symbol).sum())
        if cost_model.get("expense_ratio", {}).get("apply_daily_accrual", True):
            port_ret -= _daily_expense_drag(weights, asset_master)
        nav *= 1.0 + port_ret
        # Drift weights after returns.
        grossed = weights * (1.0 + day_ret_by_symbol)
        if grossed.sum() > 0:
            weights = grossed / grossed.sum()

        nav_rows.append({"date": dt.date(), "nav": nav, "daily_return": port_ret})

        if dt in signal_set and i < len(dates) - 1:
            tw = construct_target_weights(dt, signals, returns, asset_master, strategy, current_weights=weights)
            pending_target = tw.set_index("symbol")["target_weight"].reindex(all_symbols).fillna(0.0)
            pending_signal_date = dt

    nav_df = pd.DataFrame(nav_rows)
    trades_df = pd.DataFrame(trade_rows)
    weights_df = pd.concat(weight_rows, ignore_index=True) if weight_rows else pd.DataFrame()
    metrics = calculate_performance_metrics(nav_df, benchmark_nav=None)
    metrics["run_id"] = run_id
    metrics["strategy"] = strategy.get("name", "unknown")
    return BacktestResult(run_id=run_id, nav=nav_df, trades=trades_df, weights=weights_df, metrics=metrics)
