"""Audit helper — persist a structured event and emit a JSON log line."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_logger
from app.models.audit_log import AuditLog

logger = get_logger("audit")


async def log_audit(
    db: AsyncSession,
    *,
    event: str,
    message: str,
    user_id: int | None = None,
    severity: str = "info",
    context: dict | None = None,
) -> None:
    entry = AuditLog(
        user_id=user_id,
        event=event,
        severity=severity,
        message=message,
        context=context or {},
    )
    db.add(entry)
    await db.flush()
    logger.info(message, extra={"event": event, "user_id": user_id, **(context or {})})
