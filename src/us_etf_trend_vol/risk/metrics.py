from __future__ import annotations

import math

import numpy as np
import pandas as pd


def calculate_performance_metrics(nav: pd.DataFrame, benchmark_nav: pd.DataFrame | None = None) -> dict[str, float]:
    df = nav.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    returns = df["nav"].pct_change().fillna(0.0)
    n_days = max((df["date"].iloc[-1] - df["date"].iloc[0]).days, 1)
    years = n_days / 365.25
    start_nav = float(df["nav"].iloc[0])
    end_nav = float(df["nav"].iloc[-1])
    cagr = (end_nav / start_nav) ** (1 / years) - 1 if years > 0 and start_nav > 0 else math.nan
    annual_vol = float(returns.std(ddof=0) * np.sqrt(252))
    sharpe = float((returns.mean() * 252) / annual_vol) if annual_vol > 0 else math.nan
    downside = returns[returns < 0]
    downside_vol = float(downside.std(ddof=0) * np.sqrt(252)) if len(downside) else 0.0
    sortino = float((returns.mean() * 252) / downside_vol) if downside_vol > 0 else math.nan
    cummax = df["nav"].cummax()
    drawdown = df["nav"] / cummax - 1.0
    max_drawdown = float(drawdown.min())
    calmar = float(cagr / abs(max_drawdown)) if max_drawdown < 0 else math.nan
    monthly = df.set_index("date")["nav"].resample("ME").last().pct_change().dropna()
    monthly_win_rate = float((monthly > 0).mean()) if len(monthly) else math.nan
    return {
        "cagr": float(cagr),
        "annual_vol": annual_vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_drawdown,
        "calmar": calmar,
        "monthly_win_rate": monthly_win_rate,
        "ending_nav": end_nav,
        "num_days": float(len(df)),
    }
