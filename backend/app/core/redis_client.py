"""Redis client + lightweight pub/sub helpers for real-time signals.

Redis is used for (a) caching latest market snapshots/signals and (b) a pub/sub
bus that fans realtime events out to connected WebSocket clients.
"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger("redis")

_redis: aioredis.Redis | None = None

SIGNAL_CHANNEL = "signals"
EVENTS_CHANNEL = "events"

# Values of REDIS_URL that select the in-process fake (no external Redis needed).
_IN_MEMORY = {"", "memory", "inmemory", "fakeredis", "fake"}


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        url = (settings.redis_url or "").strip()
        if url.lower() in _IN_MEMORY:
            # Single-process in-memory Redis — lets the app run on one host with
            # no external Redis. State is per-process and resets on restart.
            import fakeredis.aioredis

            _redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
            logger.warning("REDIS_URL not set -> using in-memory Redis (ephemeral)")
        else:
            _redis = aioredis.from_url(url, encoding="utf-8", decode_responses=True)
    return _redis


async def publish(channel: str, message: dict[str, Any]) -> None:
    await get_redis().publish(channel, json.dumps(message, default=str))


async def cache_set(key: str, value: Any, ttl: int = 60) -> None:
    await get_redis().set(key, json.dumps(value, default=str), ex=ttl)


async def cache_get(key: str) -> Any | None:
    raw = await get_redis().get(key)
    return json.loads(raw) if raw else None
