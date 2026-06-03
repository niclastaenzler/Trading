"""Background scheduler — periodically runs trading cycles for active users.

Runs at a fixed tick (default 60s). The compliance guard enforces the actual
trade cadence, so a frequent tick can never translate into HFT behaviour.
Only owner accounts with auto-trading enabled and the kill switch clear are
processed.
"""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.encryption import decrypt
from app.core.logging_config import get_logger
from app.core.redis_client import get_redis
from app.models.config import TradingConfig
from app.models.user import User
from app.services.broker import get_broker
from app.services.market_data import fetch_ohlcv
from app.services.trading_engine import TradingEngine

logger = get_logger("scheduler")

TICK_SECONDS = 60
# Retrain the AI at most this often (a Redis flag, shared with the cron, spaces
# it out so a 60s tick doesn't retrain every minute).
TRAIN_INTERVAL_SECONDS = 300  # 5 minutes


async def _maybe_train(user: User, cfg_row: TradingConfig) -> None:
    """Retrain the user's model if the throttle window has elapsed."""
    redis = get_redis()
    key = f"user:{user.id}:last_model_train"
    try:
        if await redis.get(key):
            return
        from app.api.routes.research import train_user_model  # avoid import cycle
        async with SessionLocal() as db:
            await train_user_model(db, user, cfg_row.data, bars=600, max_symbols=10)
            await db.commit()
        await redis.set(key, "1", ex=TRAIN_INTERVAL_SECONDS)
        logger.info("autopilot retrained model for user %s", user.id)
    except Exception as exc:
        logger.error("training failed for user %s: %s", user.id, exc)


async def _run_user_cycle(user: User, cfg_row: TradingConfig) -> None:
    creds = {}
    if user.broker_credentials_enc:
        try:
            creds = json.loads(decrypt(user.broker_credentials_enc))
        except ValueError:
            creds = {}
    async with SessionLocal() as db:
        broker = get_broker(user.id, user.broker_name, creds)
        await broker.connect()
        engine = TradingEngine(db, user.id, cfg_row, broker)

        # 1. AI ranks the whole universe (what to trade).
        symbols = (cfg_row.data or {}).get("trading", {}).get(
            "allowed_symbols", ["EURUSD"]
        )
        ranked = await engine.scan(symbols)

        # 2. Honour protective levels on already-open positions.
        await engine.monitor_positions()

        # 3. Act on the strongest ideas first (gates limit how many open).
        for sym, df, _sig in ranked:
            await engine.process_symbol(sym, df)
        await db.commit()


async def scheduler_loop(stop_event: asyncio.Event) -> None:
    logger.info("scheduler started", extra={"tick_seconds": TICK_SECONDS})
    while not stop_event.is_set():
        try:
            async with SessionLocal() as db:
                rows = (
                    await db.execute(
                        select(User, TradingConfig)
                        .join(TradingConfig, TradingConfig.user_id == User.id)
                        .where(
                            User.is_active.is_(True),
                            User.role == "owner",
                            TradingConfig.auto_trading_enabled.is_(True),
                            TradingConfig.kill_switch_active.is_(False),
                        )
                    )
                ).all()
            for user, cfg_row in rows:
                try:
                    await _run_user_cycle(user, cfg_row)
                except Exception as exc:  # isolate per-user failures
                    logger.error("cycle failed for user %s: %s", user.id, exc)
                # Periodically retrain the AI (throttled to every 5 min).
                await _maybe_train(user, cfg_row)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("scheduler tick error: %s", exc)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=TICK_SECONDS)
        except asyncio.TimeoutError:
            pass
    logger.info("scheduler stopped")
