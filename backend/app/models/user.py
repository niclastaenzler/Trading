"""User account. Single-user focus, but the schema supports a small set of
local accounts with roles (owner/viewer)."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="owner")  # owner | viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Encrypted broker credentials (Fernet ciphertext). Never plaintext.
    broker_name: Mapped[str] = mapped_column(String(32), default="paper")
    broker_credentials_enc: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    config = relationship("TradingConfig", back_populates="user", uselist=False)
