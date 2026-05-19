from __future__ import annotations

PRICE_COLUMNS = [
    "date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
    "dividend",
    "split_factor",
    "data_vendor",
    "load_timestamp",
]

RETURNS_COLUMNS = ["date", "symbol", "adjusted_return", "log_return", "valid_return"]

SIGNALS_COLUMNS = [
    "signal_date",
    "symbol",
    "trend_score",
    "momentum_score",
    "realized_vol",
    "eligible",
    "signal_version",
    "generated_at",
]

TARGET_WEIGHT_COLUMNS = [
    "rebalance_date",
    "symbol",
    "target_weight",
    "current_weight",
    "trade_weight",
    "reason",
    "strategy_version",
]

ORDER_COLUMNS = [
    "order_date",
    "symbol",
    "side",
    "quantity",
    "estimated_price",
    "estimated_notional",
    "order_type",
    "status",
    "human_approved_by",
    "approval_timestamp",
]
