"""Redis client + lightweight pub/sub helpers for real-time signals.

Redis is used for (a) caching latest market snapshots/signals and (b) a pub/sub
bus that fans realtime events out to connected WebSocket clients.
"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

_redis: aioredis.Redis | None = None

SIGNAL_CHANNEL = "signals"
EVENTS_CHANNEL = "events"


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.redis_url, encoding="utf-8", decode_responses=True
        )
    return _redis


async def publish(channel: str, message: dict[str, Any]) -> None:
    await get_redis().publish(channel, json.dumps(message, default=str))


async def cache_set(key: str, value: Any, ttl: int = 60) -> None:
    await get_redis().set(key, json.dumps(value, default=str), ex=ttl)


async def cache_get(key: str) -> Any | None:
    raw = await get_redis().get(key)
    return json.loads(raw) if raw else None
