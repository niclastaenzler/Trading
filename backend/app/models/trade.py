"""Trade & Order records.

`Order` = an instruction sent to the broker (or simulated). `Trade` = a
position lifecycle (open -> closed) with realized PnL. Kept separate so we can
audit every broker interaction independently of position accounting.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    broker: Mapped[str] = mapped_column(String(32))
    broker_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8))  # BUY | SELL
    order_type: Mapped[str] = mapped_column(String(16), default="MARKET")
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="NEW")  # NEW|FILLED|REJECTED
    mode: Mapped[str] = mapped_column(String(8), default="paper")  # paper | live
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[float] = mapped_column(Float)

    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="OPEN")  # OPEN | CLOSED
    mode: Mapped[str] = mapped_column(String(8), default="paper")
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    strategy: Mapped[str | None] = mapped_column(String(64), nullable=True)

    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
