"""Per-user trading configuration.

The full set of tunables (trading, strategy, automation, risk, compliance) is
stored as a validated JSON document. The canonical shape + conservative
defaults live in `app.services.config_defaults.TradingConfigModel`.

Storing as JSON keeps the (large) config flexible and versionable while the
Pydantic model enforces safe bounds on read/write.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TradingConfig(Base):
    __tablename__ = "trading_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)

    # Validated TradingConfigModel serialized to JSON.
    data: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Live runtime flags kept out of `data` so the engine can flip them fast.
    auto_trading_enabled: Mapped[bool] = mapped_column(default=False)
    kill_switch_active: Mapped[bool] = mapped_column(default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="config")
