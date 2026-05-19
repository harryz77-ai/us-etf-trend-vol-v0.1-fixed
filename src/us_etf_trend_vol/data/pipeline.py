from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from us_etf_trend_vol.schema import PRICE_COLUMNS, RETURNS_COLUMNS
from us_etf_trend_vol.utils import ensure_dir


def universe_to_asset_master(universe: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(universe).copy()
    if "symbol" not in df.columns:
        raise ValueError("Universe rows require symbol")
    df["inception_date"] = pd.to_datetime(df["inception_date"], errors="coerce").dt.date
    df["active"] = df.get("active", True).astype(bool)
    return df


def validate_prices(prices: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if prices.empty:
        raise ValueError("Price table is empty")
    missing_cols = [c for c in PRICE_COLUMNS if c not in prices.columns]
    if missing_cols:
        raise ValueError(f"Missing price columns: {missing_cols}")
    out = prices[PRICE_COLUMNS].copy()
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values(["symbol", "date"]).reset_index(drop=True)

    duplicated = out.duplicated(["symbol", "date"], keep=False)
    issues = []
    if duplicated.any():
        issues.append(
            pd.DataFrame(
                {
                    "severity": "error",
                    "check": "duplicate_symbol_date",
                    "count": [int(duplicated.sum())],
                }
            )
        )
        out = out.drop_duplicates(["symbol", "date"], keep="last")
    missing_adj = out["adjusted_close"].isna()
    if missing_adj.any():
        issues.append(
            pd.DataFrame(
                {
                    "severity": "error",
                    "check": "missing_adjusted_close",
                    "count": [int(missing_adj.sum())],
                }
            )
        )
        out = out[~missing_adj]
    non_positive = out["adjusted_close"] <= 0
    if non_positive.any():
        issues.append(
            pd.DataFrame(
                {
                    "severity": "error",
                    "check": "non_positive_adjusted_close",
                    "count": [int(non_positive.sum())],
                }
            )
        )
        out = out[~non_positive]
    report = pd.concat(issues, ignore_index=True) if issues else pd.DataFrame(columns=["severity", "check", "count"])
    return out.reset_index(drop=True), report


def compute_daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    df = prices.sort_values(["symbol", "date"]).copy()
    df["adjusted_return"] = df.groupby("symbol")["adjusted_close"].pct_change().fillna(0.0)
    df["log_return"] = np.log1p(df["adjusted_return"])
    df["valid_return"] = df["adjusted_return"].abs() < 0.40
    return df[["date", "symbol", "adjusted_return", "log_return", "valid_return"]].reset_index(drop=True)


def save_table(df: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    ensure_dir(path.parent)
    if path.suffix == ".parquet":
        try:
            df.to_parquet(path, index=False)
            return path
        except Exception:
            path = path.with_suffix(".csv")
    df.to_csv(path, index=False)
    return path


def load_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def persist_data_snapshot(prices: pd.DataFrame, returns: pd.DataFrame, run_id: str) -> dict[str, str]:
    base = ensure_dir(Path("data") / "snapshots" / run_id)
    price_path = save_table(prices, base / "prices_daily.parquet")
    returns_path = save_table(returns, base / "returns_daily.parquet")
    return {"prices_daily": str(price_path), "returns_daily": str(returns_path)}
