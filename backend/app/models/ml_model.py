"""Persisted ML model — stores the trained model bytes + metadata so a trained
model survives backend restarts (the filesystem is ephemeral on free hosting)."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, JSONType


class MLModel(Base):
    __tablename__ = "ml_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    scope: Mapped[str] = mapped_column(String(32), default="global")
    # base64-encoded joblib bytes of the fitted estimator.
    model_b64: Mapped[str] = mapped_column(Text)
    features: Mapped[list] = mapped_column(JSONType, default=list)  # importances
    metrics: Mapped[dict] = mapped_column(JSONType, default=dict)
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
