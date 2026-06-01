"""Append-only audit log — every meaningful action is recorded for compliance."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, JSONType


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    # e.g. ORDER_PLACED, SIGNAL_GENERATED, COMPLIANCE_BLOCK, KILL_SWITCH, CONFIG_UPDATE
    event: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="info")
    message: Mapped[str] = mapped_column(String(512))
    context: Mapped[dict] = mapped_column(JSONType, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
