from __future__ import annotations

import pandas as pd

from us_etf_trend_vol.schema import ORDER_COLUMNS
from us_etf_trend_vol.utils import utc_now


def load_current_portfolio(path: str | None, latest_prices: pd.Series) -> pd.Series:
    if not path:
        return pd.Series(0.0, index=latest_prices.index)
    df = pd.read_csv(path)
    if not {"symbol", "quantity", "price"}.issubset(df.columns):
        raise ValueError("portfolio CSV requires symbol, quantity, price columns")
    value = (df["quantity"].astype(float) * df["price"].astype(float)).sum()
    weights = pd.Series(0.0, index=latest_prices.index)
    if value <= 0:
        return weights
    for _, row in df.iterrows():
        if row["symbol"] in weights.index:
            weights.loc[row["symbol"]] = float(row["quantity"]) * float(row["price"]) / value
    return weights


def latest_prices_from_prices(prices: pd.DataFrame) -> pd.Series:
    df = prices.copy()
    df["date"] = pd.to_datetime(df["date"])
    idx = df.sort_values("date").groupby("symbol").tail(1).set_index("symbol")
    return idx["adjusted_close"].astype(float)


def target_weights_to_orders(
    target_weights: pd.DataFrame,
    portfolio_value: float,
    latest_prices: pd.Series,
    order_type: str = "market",
    min_trade_notional: float = 100.0,
) -> pd.DataFrame:
    rows = []
    today = utc_now().date().isoformat()
    for _, row in target_weights.iterrows():
        sym = row["symbol"]
        price = float(latest_prices.get(sym, float("nan")))
        if not price or price != price or price <= 0:
            continue
        notional = float(row["trade_weight"]) * portfolio_value
        if abs(notional) < min_trade_notional:
            continue
        qty = abs(notional) / price
        rows.append(
            {
                "order_date": today,
                "symbol": sym,
                "side": "buy" if notional > 0 else "sell",
                "quantity": qty,
                "estimated_price": price,
                "estimated_notional": abs(notional),
                "order_type": order_type,
                "status": "proposed",
                "human_approved_by": "",
                "approval_timestamp": "",
            }
        )
    return pd.DataFrame(rows, columns=ORDER_COLUMNS)
