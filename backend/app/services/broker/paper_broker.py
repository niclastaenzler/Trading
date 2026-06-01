"""Paper-trading broker — the SAFE DEFAULT.

Simulates fills against a price feed and tracks positions/balance in Redis so
state survives restarts. No external orders are ever sent. This is the default
broker and the only one active until the user explicitly enables live trading.
"""

from __future__ import annotations

import json
import uuid

from app.core.redis_client import get_redis
from app.services.broker.broker_interface import (
    BrokerInterface,
    BrokerOrder,
    BrokerPosition,
)


class PaperBroker(BrokerInterface):
    name = "paper"
    is_paper = True

    def __init__(self, user_id: int, starting_balance: float = 10_000.0) -> None:
        self.user_id = user_id
        self.starting_balance = starting_balance
        self._bal_key = f"paper:{user_id}:balance"
        self._pos_key = f"paper:{user_id}:positions"
        # Latest known prices, injected by the trading engine's market feed.
        self._prices: dict[str, float] = {}

    async def connect(self) -> None:
        redis = get_redis()
        if not await redis.exists(self._bal_key):
            await redis.set(self._bal_key, self.starting_balance)

    def set_price(self, symbol: str, price: float) -> None:
        self._prices[symbol] = price

    async def get_balance(self) -> float:
        bal = await get_redis().get(self._bal_key)
        return float(bal) if bal else self.starting_balance

    async def get_price(self, symbol: str) -> float:
        return self._prices.get(symbol, 0.0)

    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> BrokerOrder:
        price = await self.get_price(symbol)
        if price <= 0:
            return BrokerOrder(
                broker_order_id="", symbol=symbol, side=side, quantity=quantity,
                price=0.0, status="REJECTED", reason="no price available",
            )
        redis = get_redis()
        positions = json.loads(await redis.get(self._pos_key) or "{}")
        positions[symbol] = {
            "symbol": symbol, "side": side, "quantity": quantity,
            "entry_price": price, "stop_loss": stop_loss, "take_profit": take_profit,
        }
        await redis.set(self._pos_key, json.dumps(positions))
        return BrokerOrder(
            broker_order_id=str(uuid.uuid4()), symbol=symbol, side=side,
            quantity=quantity, price=price, status="FILLED",
            stop_loss=stop_loss, take_profit=take_profit,
        )

    async def get_positions(self) -> list[BrokerPosition]:
        positions = json.loads(await get_redis().get(self._pos_key) or "{}")
        out = []
        for p in positions.values():
            cur = await self.get_price(p["symbol"]) or p["entry_price"]
            direction = 1 if p["side"] == "BUY" else -1
            pnl = (cur - p["entry_price"]) * p["quantity"] * direction
            out.append(
                BrokerPosition(
                    symbol=p["symbol"], side=p["side"], quantity=p["quantity"],
                    entry_price=p["entry_price"], current_price=cur,
                    unrealized_pnl=round(pnl, 2),
                    stop_loss=p.get("stop_loss"), take_profit=p.get("take_profit"),
                )
            )
        return out

    async def close_position(self, symbol: str) -> BrokerOrder:
        redis = get_redis()
        positions = json.loads(await redis.get(self._pos_key) or "{}")
        pos = positions.pop(symbol, None)
        if not pos:
            return BrokerOrder("", symbol, "", 0, 0, "REJECTED", reason="no position")
        cur = await self.get_price(symbol) or pos["entry_price"]
        direction = 1 if pos["side"] == "BUY" else -1
        pnl = (cur - pos["entry_price"]) * pos["quantity"] * direction
        balance = await self.get_balance()
        await redis.set(self._bal_key, balance + pnl)
        await redis.set(self._pos_key, json.dumps(positions))
        close_side = "SELL" if pos["side"] == "BUY" else "BUY"
        return BrokerOrder(
            broker_order_id=str(uuid.uuid4()), symbol=symbol, side=close_side,
            quantity=pos["quantity"], price=cur, status="FILLED",
            reason=f"closed pnl={round(pnl, 2)}",
        )
