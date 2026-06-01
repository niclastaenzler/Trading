"""Telegram alerts (optional bonus feature).

No-op when not configured, so the platform runs without it.
"""

from __future__ import annotations

import httpx

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger("notifications")


async def send_telegram(message: str) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                },
            )
            return resp.status_code < 400
    except Exception as exc:  # pragma: no cover - network
        logger.warning("telegram send failed: %s", exc)
        return False
