"""Token-bucket rate limiter backed by Redis (sliding window).

Used by the compliance guard to keep API usage under broker limits. Safe to
share across processes since state lives in Redis.
"""

from __future__ import annotations

import time

from app.core.redis_client import get_redis


class RateLimiter:
    def __init__(self, key: str, max_per_minute: int) -> None:
        self.key = f"ratelimit:{key}"
        self.max_per_minute = max_per_minute

    async def allow(self) -> bool:
        """Sliding-window check. Returns True if a request may proceed."""
        now = time.time()
        window_start = now - 60
        redis = get_redis()
        pipe = redis.pipeline()
        pipe.zremrangebyscore(self.key, 0, window_start)
        pipe.zadd(self.key, {f"{now}": now})
        pipe.zcard(self.key)
        pipe.expire(self.key, 60)
        _, _, count, _ = await pipe.execute()
        return count <= self.max_per_minute

    async def remaining(self) -> int:
        redis = get_redis()
        await redis.zremrangebyscore(self.key, 0, time.time() - 60)
        count = await redis.zcard(self.key)
        return max(0, self.max_per_minute - count)
