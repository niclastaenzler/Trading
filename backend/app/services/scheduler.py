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
from app.models.config import TradingConfig
from app.models.user import User
from app.services.broker import get_broker
from app.services.market_data import fetch_ohlcv
from app.services.trading_engine import TradingEngine

logger = get_logger("scheduler")

TICK_SECONDS = 60


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

        # 1. Honour protective levels on already-open positions.
        await engine.monitor_positions()

        # 2. Look for new entries.
        symbols = (cfg_row.data or {}).get("trading", {}).get(
            "allowed_symbols", ["EURUSD"]
        )
        for symbol in symbols:
            ohlcv = await fetch_ohlcv(symbol, bars=200, broker=broker)
            await engine.process_symbol(symbol, ohlcv)
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
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("scheduler tick error: %s", exc)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=TICK_SECONDS)
        except asyncio.TimeoutError:
            pass
    logger.info("scheduler stopped")
