"""Abstract broker layer.

All brokers (paper, Capital.com, future MetaTrader/TradingView bridges) implement
this interface so the trading engine stays broker-agnostic. Only officially
documented broker APIs may back a concrete implementation — no scraping.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class BrokerOrder:
    broker_order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    status: str  # FILLED | NEW | REJECTED
    stop_loss: float | None = None
    take_profit: float | None = None
    reason: str | None = None


@dataclass
class BrokerPosition:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float


class BrokerInterface(abc.ABC):
    name: str = "abstract"
    is_paper: bool = True

    @abc.abstractmethod
    async def connect(self) -> None:
        """Authenticate / open a session."""

    @abc.abstractmethod
    async def get_balance(self) -> float:
        """Account equity in account currency."""

    @abc.abstractmethod
    async def get_price(self, symbol: str) -> float:
        """Latest mid price for `symbol`."""

    @abc.abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> BrokerOrder:
        """Submit a market order with attached protective stop/target."""

    @abc.abstractmethod
    async def get_positions(self) -> list[BrokerPosition]:
        ...

    @abc.abstractmethod
    async def close_position(self, symbol: str) -> BrokerOrder:
        ...
