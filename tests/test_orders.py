import pandas as pd

from us_etf_trend_vol.execution.orders import target_weights_to_orders


def test_orders_generated():
    target = pd.DataFrame(
        {
            "symbol": ["SPY", "BIL"],
            "trade_weight": [0.10, -0.10],
        }
    )
    prices = pd.Series({"SPY": 500.0, "BIL": 91.0})
    orders = target_weights_to_orders(target, 100000, prices, min_trade_notional=100)
    assert len(orders) == 2
    assert set(orders["side"]) == {"buy", "sell"}
