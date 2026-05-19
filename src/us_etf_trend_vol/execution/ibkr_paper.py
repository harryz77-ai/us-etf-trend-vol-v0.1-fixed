from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class IbkrConfig:
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 77
    exchange: str = "SMART"
    currency: str = "USD"
    account: str | None = None
    allow_fractional_shares: bool = False
    transmit: bool = True


class IbkrPaperTrader:
    """Guarded IBKR paper order adapter.

    This adapter uses ib_async if installed. It intentionally does not connect or submit orders at import time.
    """

    def __init__(self, config: IbkrConfig) -> None:
        self.config = config

    def submit_orders(self, orders: pd.DataFrame, submit: bool, approval_phrase: bool) -> list[dict]:
        if not submit:
            return [
                {"symbol": row.symbol, "side": row.side, "quantity": row.quantity, "status": "dry_run"}
                for row in orders.itertuples(index=False)
            ]
        if not approval_phrase:
            raise PermissionError("IBKR paper submission requires --i-understand-paper-trading")
        try:
            from ib_async import IB, MarketOrder, Stock
        except ImportError as exc:
            raise RuntimeError("Install optional dependency: pip install -e .[ibkr]") from exc

        ib = IB()
        ib.connect(self.config.host, self.config.port, clientId=self.config.client_id)
        results: list[dict] = []
        try:
            for row in orders.itertuples(index=False):
                qty = float(row.quantity)
                if not self.config.allow_fractional_shares:
                    qty = int(qty)
                if qty <= 0:
                    continue
                action = "BUY" if row.side == "buy" else "SELL"
                contract = Stock(row.symbol, self.config.exchange, self.config.currency)
                order = MarketOrder(action, qty)
                order.transmit = bool(self.config.transmit)
                if self.config.account:
                    order.account = self.config.account
                trade = ib.placeOrder(contract, order)
                ib.sleep(1)
                results.append(
                    {
                        "symbol": row.symbol,
                        "side": row.side,
                        "quantity": qty,
                        "status": str(trade.orderStatus.status),
                        "order_id": trade.order.orderId,
                    }
                )
        finally:
            ib.disconnect()
        return results


def parse_ibkr_config(strategy: dict) -> IbkrConfig:
    raw = strategy.get("execution", {}).get("ibkr", {})
    return IbkrConfig(
        host=raw.get("host", "127.0.0.1"),
        port=int(raw.get("port", 7497)),
        client_id=int(raw.get("client_id", 77)),
        exchange=raw.get("exchange", "SMART"),
        currency=raw.get("currency", "USD"),
        account=raw.get("account"),
        allow_fractional_shares=bool(raw.get("allow_fractional_shares", False)),
        transmit=bool(raw.get("transmit", True)),
    )
