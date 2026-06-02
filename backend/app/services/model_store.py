"""Persist / load the trained ML model to the database (survives restarts)."""

from __future__ import annotations

import base64

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_logger
from app.models.ml_model import MLModel
from app.services.ai_engine import ai_model

logger = get_logger("model_store")


async def save_model(db: AsyncSession, user_id: int, features: list, metrics: dict) -> bool:
    blob = ai_model.dumps()
    if blob is None:
        return False
    db.add(
        MLModel(
            user_id=user_id,
            scope="global",
            model_b64=base64.b64encode(blob).decode(),
            features=features,
            metrics=metrics,
        )
    )
    await db.flush()
    return True


async def latest_model_row(db: AsyncSession) -> MLModel | None:
    res = await db.execute(select(MLModel).order_by(desc(MLModel.trained_at)).limit(1))
    return res.scalar_one_or_none()


async def load_latest_model(db: AsyncSession) -> bool:
    """Load the most recently trained model into the live AI engine."""
    row = await latest_model_row(db)
    if not row or not row.model_b64:
        return False
    ok = ai_model.loads(base64.b64decode(row.model_b64))
    if ok:
        logger.info("loaded trained model from DB", extra={"trained_at": str(row.trained_at)})
    return ok
