from datetime import datetime

from pydantic import BaseModel


class TradeOut(BaseModel):
    id: int
    symbol: str
    side: str
    quantity: float
    entry_price: float
    exit_price: float | None
    stop_loss: float | None
    take_profit: float | None
    status: str
    mode: str
    pnl: float | None
    confidence: float | None
    strategy: str | None
    opened_at: datetime
    closed_at: datetime | None

    class Config:
        from_attributes = True


class OrderOut(BaseModel):
    id: int
    symbol: str
    side: str
    quantity: float
    price: float | None
    status: str
    mode: str
    reason: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class PerformanceOut(BaseModel):
    equity: float
    open_positions: int
    realized_pnl_today: float
    total_trades: int
    win_rate: float
    total_pnl: float


class BrokerCredentials(BaseModel):
    broker: str  # paper | capital_com
    api_key: str | None = None
    identifier: str | None = None
    password: str | None = None
    demo: bool = True
