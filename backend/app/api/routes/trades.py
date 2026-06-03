"""Trade history, orders, performance analytics and broker credential setup."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_owner
from app.core.database import get_db
from app.core.encryption import decrypt, encrypt
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
    # Read equity/positions from the user's ACTUAL broker (Capital.com etc.),
    # falling back to paper if the live broker is unreachable.
    broker = _build_user_broker(user)
    try:
        await broker.connect()
        equity = await broker.get_balance()
        positions = await broker.get_positions()
    except Exception:
        paper = get_broker(user.id, "paper")
        await paper.connect()
        equity = await paper.get_balance()
        positions = await paper.get_positions()
    finally:
        if hasattr(broker, "aclose"):
            await broker.aclose()

    # Pull all closed-trade PnLs (chronological) and derive metrics in Python.
    rows = (
        await db.execute(
            select(Trade.pnl, Trade.closed_at).where(
                Trade.user_id == user.id, Trade.status == "CLOSED", Trade.pnl.isnot(None)
            ).order_by(Trade.closed_at.asc())
        )
    ).all()
    pnls = [float(p) for p, _ in rows]

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit, gross_loss = sum(wins), abs(sum(losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss else (999.0 if gross_profit else 0.0)

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    def _aware(dt):
        # SQLite returns naive datetimes even for timezone=True columns; assume
        # UTC so the comparison is valid on both SQLite and PostgreSQL.
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    realized_today = sum(p for p, closed in rows if closed and _aware(closed) >= today)

    cum, equity_curve = 0.0, []
    for p in pnls:
        cum += p
        equity_curve.append(round(cum, 2))

    return PerformanceOut(
        equity=round(equity, 2),
        open_positions=len(positions),
        realized_pnl_today=round(realized_today, 2),
        total_trades=len(pnls),
        win_rate=round(len(wins) / len(pnls), 4) if pnls else 0.0,
        total_pnl=round(sum(pnls), 2),
        profit_factor=round(profit_factor, 3),
        avg_win=round(sum(wins) / len(wins), 2) if wins else 0.0,
        avg_loss=round(sum(losses) / len(losses), 2) if losses else 0.0,
        best_trade=round(max(pnls), 2) if pnls else 0.0,
        worst_trade=round(min(pnls), 2) if pnls else 0.0,
        equity_curve=equity_curve,
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


def _build_user_broker(user: User):
    """Construct the user's configured broker with decrypted credentials."""
    creds = {}
    if user.broker_credentials_enc:
        try:
            creds = json.loads(decrypt(user.broker_credentials_enc))
        except ValueError:
            creds = {}
    return get_broker(user.id, user.broker_name, creds)


@router.get("/broker")
async def broker_status(user: User = Depends(get_current_user)):
    """Current broker selection (no secrets returned)."""
    return {
        "broker": user.broker_name,
        "configured": bool(user.broker_credentials_enc) or user.broker_name == "paper",
    }


@router.post("/broker/test")
async def broker_test(user: User = Depends(require_owner)):
    """Try to connect to the configured broker and read the balance."""
    broker = _build_user_broker(user)
    try:
        await broker.connect()
        balance = await broker.get_balance()
        return {"ok": True, "broker": broker.name, "is_paper": broker.is_paper,
                "balance": round(float(balance), 2)}
    except Exception as exc:  # surface a readable reason to the UI
        return {"ok": False, "broker": broker.name, "error": str(exc)[:300]}
    finally:
        if hasattr(broker, "aclose"):
            await broker.aclose()


@router.get("/positions")
async def open_positions(user: User = Depends(get_current_user)):
    """Live open positions from the active broker."""
    broker = _build_user_broker(user)
    try:
        await broker.connect()
        positions = await broker.get_positions()
        return [
            {
                "symbol": p.symbol, "side": p.side, "quantity": p.quantity,
                "entry_price": round(p.entry_price, 6),
                "current_price": round(p.current_price, 6),
                "unrealized_pnl": round(p.unrealized_pnl, 2),
                "stop_loss": p.stop_loss, "take_profit": p.take_profit,
            }
            for p in positions
        ]
    except Exception:
        return []
    finally:
        if hasattr(broker, "aclose"):
            await broker.aclose()


@router.get("/account")
async def account_info(user: User = Depends(get_current_user)):
    """Account summary from the active broker: balance, open positions, mode."""
    broker = _build_user_broker(user)
    try:
        await broker.connect()
        acc = await broker.get_account()
        positions = await broker.get_positions()
        return {
            "broker": broker.name,
            "mode": "demo/paper" if broker.is_paper else "LIVE",
            "is_paper": broker.is_paper,
            # equity = Kontowert; available = freie Margin; used_margin = genutzt
            "equity": round(float(acc.get("equity", 0.0)), 2),
            "available": round(float(acc.get("available", 0.0)), 2),
            "used_margin": round(float(acc.get("used_margin", 0.0)), 2),
            "profit_loss": round(float(acc.get("profit_loss", 0.0)), 2),
            "currency": acc.get("currency", ""),
            "balance": round(float(acc.get("equity", 0.0)), 2),  # back-compat
            "open_positions": len(positions),
            "unrealized_pnl": round(sum(p.unrealized_pnl for p in positions), 2),
            "ok": True,
        }
    except Exception as exc:
        return {"broker": broker.name, "ok": False, "error": str(exc)[:200]}
    finally:
        if hasattr(broker, "aclose"):
            await broker.aclose()
