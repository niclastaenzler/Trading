"""Trading control routes: run a cycle, manage pending (semi-auto) trades,
close positions."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_user_config, require_owner
from app.core.database import get_db
from app.core.encryption import decrypt
from app.core.redis_client import get_redis
from app.models.config import TradingConfig
from app.models.user import User
from app.schemas.signal import PendingConfirm
from app.services.broker import get_broker
from app.services.market_data import fetch_ohlcv
from app.services.risk_manager import TradePlan
from app.services.trading_engine import TradingEngine

router = APIRouter(prefix="/api/trading", tags=["trading"])


def _build_broker(user: User):
    creds = {}
    if user.broker_credentials_enc:
        try:
            creds = json.loads(decrypt(user.broker_credentials_enc))
        except ValueError:
            creds = {}
    return get_broker(user.id, user.broker_name, creds)


@router.post("/run-cycle")
async def run_cycle(
    cfg: TradingConfig = Depends(get_user_config),
    user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """Run one decision cycle across all configured symbols.

    Intended to be invoked by a scheduler at the user's chosen interval (the
    compliance guard enforces safe cadence regardless of how often it's called).
    """
    broker = _build_broker(user)
    await broker.connect()
    engine = TradingEngine(db, user.id, cfg, broker)
    symbols = cfg.data.get("trading", {}).get("allowed_symbols", ["EURUSD"])

    results = []
    for symbol in symbols:
        ohlcv = await fetch_ohlcv(symbol, bars=200)
        results.append(await engine.process_symbol(symbol, ohlcv))
    return {"cycle": "complete", "results": results}


@router.get("/pending")
async def list_pending(
    cfg: TradingConfig = Depends(get_user_config),
    user: User = Depends(require_owner),
):
    redis = get_redis()
    pending = []
    async for key in redis.scan_iter(f"user:{user.id}:pending:*"):
        raw = await redis.get(key)
        if raw:
            pending.append(json.loads(raw))
    return {"pending": pending}


@router.post("/confirm")
async def confirm_pending(
    body: PendingConfirm,
    cfg: TradingConfig = Depends(get_user_config),
    user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject a queued semi-auto trade proposal."""
    redis = get_redis()
    key = f"user:{user.id}:pending:{body.symbol}"
    raw = await redis.get(key)
    if not raw:
        raise HTTPException(404, "No pending trade for symbol")
    await redis.delete(key)

    if not body.approve:
        return {"action": "rejected", "symbol": body.symbol}

    data = json.loads(raw)
    plan = TradePlan(**data["plan"])
    broker = _build_broker(user)
    await broker.connect()
    if hasattr(broker, "set_price"):
        broker.set_price(plan.symbol, plan.entry_price)
    engine = TradingEngine(db, user.id, cfg, broker)
    return await engine.execute_plan(plan, data.get("confidence", 0.0))


@router.post("/close/{symbol}")
async def close_position(
    symbol: str,
    user: User = Depends(require_owner),
):
    broker = _build_broker(user)
    await broker.connect()
    order = await broker.close_position(symbol)
    return {"status": order.status, "reason": order.reason}
