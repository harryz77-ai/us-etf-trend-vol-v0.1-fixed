from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _cap_and_renormalize(weights: pd.Series, caps: pd.Series | float, max_iter: int = 20) -> pd.Series:
    if isinstance(caps, (int, float)):
        caps = pd.Series(float(caps), index=weights.index)
    w = weights.clip(lower=0).astype(float)
    if w.sum() <= 0:
        return w
    w = w / w.sum()
    for _ in range(max_iter):
        over = w > caps
        if not over.any():
            break
        excess = (w[over] - caps[over]).sum()
        w[over] = caps[over]
        under = ~over
        if under.any() and excess > 0:
            room = (caps[under] - w[under]).clip(lower=0)
            if room.sum() > 0:
                w[under] += excess * room / room.sum()
    return w


def _apply_asset_class_caps(weights: pd.Series, asset_master: pd.DataFrame, class_caps: dict[str, float]) -> pd.Series:
    meta = asset_master.set_index("symbol")
    w = weights.copy()
    for _ in range(10):
        changed = False
        for cls, cap in class_caps.items():
            members = [s for s in w.index if meta.loc[s, "asset_class"] == cls]
            if not members:
                continue
            total = w[members].sum()
            if total > cap + 1e-12:
                scale = cap / total
                reduction = total - cap
                w[members] *= scale
                others = [s for s in w.index if s not in members]
                if others:
                    room = pd.Series(1.0, index=others) - w[others]
                    room = room.clip(lower=0)
                    if room.sum() > 0:
                        w[others] += reduction * room / room.sum()
                changed = True
        if not changed:
            break
    if w.sum() > 0:
        w = w / w.sum()
    return w


def _estimate_portfolio_vol(
    returns: pd.DataFrame,
    signal_date: pd.Timestamp,
    weights: pd.Series,
    lookback_days: int,
) -> float:
    r = returns.copy()
    r["date"] = pd.to_datetime(r["date"])
    subset = r[(r["date"] <= signal_date) & (r["symbol"].isin(weights.index))]
    wide = subset.pivot(index="date", columns="symbol", values="adjusted_return").tail(lookback_days)
    wide = wide[weights.index].dropna(how="all").fillna(0.0)
    if len(wide) < max(20, lookback_days // 3):
        return math.nan
    cov = wide.cov().values * 252
    w = weights.values.reshape(-1, 1)
    var = float((w.T @ cov @ w).item())
    return math.sqrt(max(var, 0.0))


def construct_target_weights(
    signal_date: pd.Timestamp,
    signals: pd.DataFrame,
    returns: pd.DataFrame,
    asset_master: pd.DataFrame,
    strategy: dict,
    current_weights: pd.Series | None = None,
) -> pd.DataFrame:
    limits = strategy["risk_limits"]
    pcfg = strategy["portfolio_construction"]
    cash = strategy["cash_asset"]
    s = signals.copy()
    s["signal_date"] = pd.to_datetime(s["signal_date"])
    latest = s[s["signal_date"] == pd.to_datetime(signal_date)].copy()
    if latest.empty:
        raise ValueError(f"No signals for {signal_date}")

    meta = asset_master.set_index("symbol")
    risk_assets = latest[latest["symbol"] != cash].copy()
    if pcfg.get("require_positive_trend", True):
        risk_assets = risk_assets[risk_assets["eligible"] & (risk_assets["trend_score"] > 0)]
    else:
        risk_assets = risk_assets[risk_assets["eligible"]]

    all_symbols = list(meta.index)
    target = pd.Series(0.0, index=all_symbols, dtype=float)
    reason = {sym: "not_eligible_or_zero_weight" for sym in all_symbols}

    if not risk_assets.empty:
        inv_vol = 1 / risk_assets.set_index("symbol")["realized_vol"].replace(0, np.nan)
        inv_vol = inv_vol.replace([np.inf, -np.inf], np.nan).dropna()
        inv_vol = inv_vol[inv_vol > 0]
        if not inv_vol.empty:
            raw = inv_vol / inv_vol.sum()
            raw = _cap_and_renormalize(raw, float(limits["max_single_asset_weight"]))
            raw = _apply_asset_class_caps(raw, asset_master, limits.get("max_asset_class_weight", {}))
            vol = _estimate_portfolio_vol(
                returns=returns,
                signal_date=pd.to_datetime(signal_date),
                weights=raw,
                lookback_days=int(pcfg.get("volatility_targeting", {}).get("lookback_days", 63)),
            )
            gross = 1.0
            vt = pcfg.get("volatility_targeting", {})
            if vt.get("enabled", True) and vol and not math.isnan(vol) and vol > 0:
                gross = float(limits["target_annual_volatility"]) / vol
                gross = min(float(limits["max_gross_exposure"]), max(float(limits["min_gross_exposure"]), gross))
            raw = raw * gross
            target.loc[raw.index] = raw
            for sym in raw.index:
                reason[sym] = "eligible_positive_trend_inverse_vol_weighted"

    cash_weight = 1.0 - target.sum()
    if cash in target.index:
        target.loc[cash] = max(0.0, cash_weight)
        reason[cash] = "cash_residual_or_defensive_allocation"
    else:
        target = target / target.sum() if target.sum() else target

    if current_weights is None:
        current_weights = pd.Series(0.0, index=target.index)
    current_weights = current_weights.reindex(target.index).fillna(0.0)
    min_trade = float(limits.get("min_trade_weight", 0.0))
    trade = target - current_weights
    trade = trade.where(trade.abs() >= min_trade, 0.0)

    return pd.DataFrame(
        {
            "rebalance_date": pd.to_datetime(signal_date).date(),
            "symbol": target.index,
            "target_weight": target.values,
            "current_weight": current_weights.values,
            "trade_weight": trade.values,
            "reason": [reason[sym] for sym in target.index],
            "strategy_version": strategy.get("version", "0.1"),
        }
    )
