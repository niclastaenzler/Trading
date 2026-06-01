from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    side: str
    quantity: float
    price: float | None
    status: str
    mode: str
    reason: str | None
    created_at: datetime


class PerformanceOut(BaseModel):
    equity: float
    open_positions: int
    realized_pnl_today: float
    total_trades: int
    win_rate: float
    total_pnl: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    best_trade: float
    worst_trade: float
    # Cumulative realized-PnL curve built from closed trades (for charting).
    equity_curve: list[float] = []


class BrokerCredentials(BaseModel):
    broker: str  # paper | capital_com
    api_key: str | None = None
    identifier: str | None = None
    password: str | None = None
    demo: bool = True
