"""Trade history, orders, performance analytics and broker credential setup."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_owner
from app.core.database import get_db
from app.core.encryption import encrypt
from app.models.trade import Order, Trade
from app.models.user import User
from app.schemas.trade import (
    BrokerCredentials,
    OrderOut,
    PerformanceOut,
    TradeOut,
)
from app.services.audit import log_audit
from app.services.broker import get_broker

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("", response_model=list[TradeOut])
async def list_trades(
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Trade).where(Trade.user_id == user.id)
        .order_by(desc(Trade.opened_at)).limit(limit)
    )
    return list(result.scalars().all())


@router.get("/orders", response_model=list[OrderOut])
async def list_orders(
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).where(Order.user_id == user.id)
        .order_by(desc(Order.created_at)).limit(limit)
    )
    return list(result.scalars().all())


@router.get("/performance", response_model=PerformanceOut)
async def performance(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    broker = get_broker(user.id, "paper")  # account view; live read is opt-in
    await broker.connect()
    equity = await broker.get_balance()
    positions = await broker.get_positions()

    total = await db.scalar(
        select(func.count(Trade.id)).where(
            Trade.user_id == user.id, Trade.status == "CLOSED"
        )
    ) or 0
    wins = await db.scalar(
        select(func.count(Trade.id)).where(
            Trade.user_id == user.id, Trade.status == "CLOSED", Trade.pnl > 0
        )
    ) or 0
    total_pnl = await db.scalar(
        select(func.coalesce(func.sum(Trade.pnl), 0.0)).where(
            Trade.user_id == user.id, Trade.status == "CLOSED"
        )
    ) or 0.0

    return PerformanceOut(
        equity=round(equity, 2),
        open_positions=len(positions),
        realized_pnl_today=0.0,
        total_trades=total,
        win_rate=round(wins / total, 4) if total else 0.0,
        total_pnl=round(float(total_pnl), 2),
    )


@router.post("/broker")
async def set_broker(
    body: BrokerCredentials,
    user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """Store (encrypted) broker credentials and switch the active broker.

    Live brokers are accepted but trading still requires the user to enable
    auto-trading and clear the kill switch.
    """
    user.broker_name = body.broker
    if body.broker == "paper":
        user.broker_credentials_enc = None
    else:
        creds = {
            "api_key": body.api_key,
            "identifier": body.identifier,
            "password": body.password,
            "demo": body.demo,
        }
        user.broker_credentials_enc = encrypt(json.dumps(creds))
    await log_audit(db, event="BROKER_CONFIGURED", user_id=user.id,
                    message=f"broker set to {body.broker} (demo={body.demo})")
    return {"broker": user.broker_name, "demo": body.demo}
