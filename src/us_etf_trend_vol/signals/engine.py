from __future__ import annotations

import numpy as np
import pandas as pd

from us_etf_trend_vol.schema import SIGNALS_COLUMNS
from us_etf_trend_vol.utils import utc_now


def _month_end_prices(prices: pd.DataFrame) -> pd.DataFrame:
    df = prices.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["symbol", "date"])
    idx = df.groupby(["symbol", df["date"].dt.to_period("M")])["date"].idxmax()
    monthly = df.loc[idx, ["date", "symbol", "adjusted_close"]].rename(columns={"date": "signal_date"})
    return monthly.sort_values(["symbol", "signal_date"]).reset_index(drop=True)


def generate_monthly_signals(
    prices: pd.DataFrame,
    returns: pd.DataFrame,
    strategy: dict,
) -> pd.DataFrame:
    signal_cfg = strategy["signals"]
    trend_lookbacks = signal_cfg["trend"].get("lookbacks_months", [10])
    momentum_lookbacks = signal_cfg["momentum"].get("lookbacks_months", [6, 12])
    vol_lookback = int(signal_cfg["volatility"].get("lookback_days", 63))
    ann = int(signal_cfg["volatility"].get("annualization_factor", 252))
    min_history_months = int(strategy["portfolio_construction"].get("require_min_history_months", 12))

    monthly = _month_end_prices(prices)
    rows = []
    for symbol, sdf in monthly.groupby("symbol", sort=False):
        sdf = sdf.sort_values("signal_date").copy()
        price = sdf["adjusted_close"]
        trend_parts = []
        for lb in trend_lookbacks:
            ma = price.rolling(lb, min_periods=lb).mean()
            trend_parts.append((price > ma).astype(float))
        trend_score = pd.concat(trend_parts, axis=1).mean(axis=1)

        mom_parts = []
        for lb in momentum_lookbacks:
            mom_parts.append(price.pct_change(lb))
        momentum_score = pd.concat(mom_parts, axis=1).mean(axis=1)

        temp = sdf[["signal_date", "symbol"]].copy()
        temp["trend_score"] = trend_score.to_numpy()
        temp["momentum_score"] = momentum_score.to_numpy()
        rows.append(temp)
    signals = pd.concat(rows, ignore_index=True)

    r = returns.copy()
    r["date"] = pd.to_datetime(r["date"])
    r = r.sort_values(["symbol", "date"])
    r["realized_vol"] = (
        r.groupby("symbol")["adjusted_return"].rolling(vol_lookback, min_periods=vol_lookback).std().reset_index(level=0, drop=True)
        * np.sqrt(ann)
    )
    # Align latest known daily vol to each monthly signal date.
    vol_frames = []
    for symbol, sdf in signals.groupby("symbol"):
        left = sdf[["signal_date", "symbol"]].sort_values("signal_date")
        right = r.loc[r["symbol"] == symbol, ["date", "realized_vol"]].sort_values("date")
        merged = pd.merge_asof(left, right, left_on="signal_date", right_on="date", direction="backward")
        vol_frames.append(merged[["signal_date", "symbol", "realized_vol"]])
    vol = pd.concat(vol_frames, ignore_index=True)
    signals = signals.merge(vol, on=["signal_date", "symbol"], how="left")

    signals["eligible"] = (
        signals["trend_score"].fillna(0) > 0
    ) & signals["momentum_score"].notna() & signals["realized_vol"].notna()

    # Enforce minimum monthly history.
    signals["month_count"] = signals.groupby("symbol").cumcount() + 1
    signals.loc[signals["month_count"] < min_history_months, "eligible"] = False
    signals["signal_version"] = strategy.get("version", "0.1")
    signals["generated_at"] = utc_now().isoformat()
    return signals[SIGNALS_COLUMNS].sort_values(["signal_date", "symbol"]).reset_index(drop=True)
