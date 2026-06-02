"""News / sentiment overlay — Alpha Vantage provider (optional).

If ALPHAVANTAGE_API_KEY is set, `get_sentiment(symbol)` fetches recent news
sentiment for the instrument and returns an aggregate score in [-1, 1] (cached
in Redis to respect rate limits). Without a key — or on any error — it returns
NEUTRAL (0.0), so the overlay has no effect until a real source is connected.

Coverage note: news sentiment is strongest for stocks/crypto and thin for FX.
"""

from __future__ import annotations

import httpx

from app.config import settings
from app.core.logging_config import get_logger
from app.core.redis_client import cache_get, cache_set

logger = get_logger("sentiment")

NEUTRAL = 0.0
_BASE = "https://www.alphavantage.co/query"
_CACHE_TTL = 1800  # 30 minutes


def is_active() -> bool:
    """Whether a real sentiment source is connected."""
    return bool(settings.alphavantage_api_key)


def _to_av_ticker(symbol: str) -> str:
    """Map our symbols to Alpha Vantage news tickers (best-effort)."""
    s = symbol.upper()
    if s.endswith("USD") and len(s) == 6:  # forex pair like EURUSD
        return f"FOREX:{s[:3]}"
    crypto = {"BTCUSD": "CRYPTO:BTC", "ETHUSD": "CRYPTO:ETH"}
    if s in crypto:
        return crypto[s]
    return s  # plain equity ticker (AAPL, TSLA, …)


async def get_sentiment(symbol: str) -> float:
    """Aggregate recent news sentiment for `symbol` in [-1, 1]; neutral if no
    source / no data / error."""
    if not is_active():
        return NEUTRAL

    cache_key = f"sentiment:{symbol}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return float(cached)

    ticker = _to_av_ticker(symbol)
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(
                _BASE,
                params={
                    "function": "NEWS_SENTIMENT",
                    "tickers": ticker,
                    "apikey": settings.alphavantage_api_key,
                    "limit": 50,
                },
            )
        data = resp.json()
        feed = data.get("feed", []) or []
        scores: list[float] = []
        for item in feed:
            for ts in item.get("ticker_sentiment", []) or []:
                if ts.get("ticker") == ticker:
                    try:
                        scores.append(float(ts.get("ticker_sentiment_score", 0.0)))
                    except (TypeError, ValueError):
                        pass
        score = max(-1.0, min(1.0, sum(scores) / len(scores))) if scores else NEUTRAL
    except Exception as exc:  # network / parse / rate-limit
        logger.warning("sentiment fetch failed for %s: %s", symbol, exc)
        score = NEUTRAL

    await cache_set(cache_key, score, ttl=_CACHE_TTL)
    return score
