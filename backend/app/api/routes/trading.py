"""Trading control routes: run a cycle, manage pending (semi-auto) trades,
close positions."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_user_config, require_owner
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

    # AI ranks the whole universe; we act on the strongest ideas first. The
    # max-open-positions / risk / compliance gates limit how many actually open.
    ranked = await engine.scan(symbols)
    closed = await engine.monitor_positions()
    results = []
    for sym, df, _sig in ranked:
        results.append(await engine.process_symbol(sym, df))
    return {"cycle": "complete", "closed": closed, "results": results}


@router.get("/scan")
async def scan_market(
    cfg: TradingConfig = Depends(get_user_config),
    user: User = Depends(get_current_user),
):
    """KI-Marktanalyse: rank every configured symbol best-first without trading.
    Shows WHAT the AI would trade and why the rest is skipped."""
    broker = _build_broker(user)
    try:
        await broker.connect()
    except Exception:
        pass
    from app.services.trading_engine import TradingEngine as _TE  # local import ok

    engine = _TE(None, user.id, cfg, broker)  # no DB needed for a read-only scan
    symbols = cfg.data.get("trading", {}).get("allowed_symbols", ["EURUSD"])
    try:
        ranked = await engine.scan(symbols)
    finally:
        if hasattr(broker, "aclose"):
            await broker.aclose()

    # Cross-sectional relative strength: rank each symbol's 20-bar momentum
    # against the rest of the scanned universe (0..1 percentile).
    moms = {}
    for s, df, _sig in ranked:
        try:
            moms[s] = float(df["close"].iloc[-1] / df["close"].iloc[-21] - 1)
        except Exception:
            moms[s] = 0.0
    ordered = sorted(moms.values())
    n = len(ordered)

    def rel_strength(sym: str) -> float:
        if n <= 1:
            return 0.5
        rank = sum(1 for v in ordered if v <= moms[sym])
        return round(rank / n, 3)

    def reason(sig) -> str:
        c = sig.components or {}
        if sig.actionable:
            return ""
        if c.get("vetoed_by_trend"):
            return "gegen Trend"
        if c.get("below_threshold"):
            return "unter Konfidenzschwelle"
        if c.get("edge_rejected"):
            return c["edge_rejected"]
        return "kein klares Signal"

    return {
        "opportunities": [
            {
                "symbol": s,
                "action": "BUY" if sig.direction > 0 else ("SELL" if sig.direction < 0 else "—"),
                "direction": sig.direction,
                "confidence": round(sig.confidence, 4),
                "edge_score": round(sig.edge_score, 4),
                "rel_strength": rel_strength(s),
                "regime": (sig.components.get("regime") or {}).get("regime", "—"),
                "price": round(sig.price, 6),
                "actionable": sig.actionable,
                "reason": reason(sig),
            }
            for (s, _df, sig) in ranked
        ]
    }


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
    cfg: TradingConfig = Depends(get_user_config),
    user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    broker = _build_broker(user)
    await broker.connect()
    engine = TradingEngine(db, user.id, cfg, broker)
    return await engine.close_position(symbol, reason="manual")
