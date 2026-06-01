"""TradingView webhook integration (bonus).

TradingView alerts POST a small JSON payload here. The shared secret
authenticates the request; the external signal is then routed through the SAME
risk + compliance pipeline as internal signals — external sources get no
special treatment.

Example alert message (TradingView "Webhook URL" + alert body):
    {"secret": "...", "symbol": "EURUSD", "side": "BUY", "confidence": 0.8}
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.models.config import TradingConfig
from app.models.user import User
from app.services.broker import get_broker
from app.services.compliance_guard import ComplianceGuard
from app.services.config_defaults import TradingConfigModel
from app.services.market_data import fetch_ohlcv
from app.services.risk_manager import RiskManager
from app.services.signal_engine import Signal
from app.services.trading_engine import TradingEngine
from app.analysis import indicators

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


class TradingViewAlert(BaseModel):
    secret: str
    symbol: str
    side: str  # BUY | SELL
    confidence: float = 0.8


@router.post("/tradingview")
async def tradingview(alert: TradingViewAlert, db: AsyncSession = Depends(get_db)):
    if alert.secret != settings.tradingview_webhook_secret:
        raise HTTPException(401, "Invalid webhook secret")

    # Route to the owner account (single-user focus).
    user = (await db.execute(select(User).where(User.role == "owner"))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "No owner account configured")
    cfg_row = (
        await db.execute(select(TradingConfig).where(TradingConfig.user_id == user.id))
    ).scalar_one_or_none()
    if not cfg_row:
        raise HTTPException(404, "No config for owner")

    cfg = TradingConfigModel(**(cfg_row.data or {}))

    # Build a signal from current market context for price/ATR.
    ohlcv = await fetch_ohlcv(alert.symbol, bars=200)
    enriched = indicators.compute_all(ohlcv, cfg.strategy.indicators)
    last = enriched.iloc[-1]
    direction = 1 if alert.side.upper() == "BUY" else -1
    signal = Signal(
        symbol=alert.symbol, direction=direction, confidence=alert.confidence,
        price=float(last["close"]), atr=float(last["atr"]),
        components={"source": "tradingview"},
    )

    broker = get_broker(user.id, "paper")  # external signals default to paper
    await broker.connect()
    if hasattr(broker, "set_price"):
        broker.set_price(alert.symbol, signal.price)
    engine = TradingEngine(db, user.id, cfg_row, broker)

    # Reuse engine plumbing: build plan, validate, gate, execute.
    equity = await broker.get_balance()
    plan = engine.risk.build_plan(signal, equity)
    verdict = engine.risk.validate(
        plan, open_positions=len(await broker.get_positions()),
        equity=equity, realized_pnl_today=0.0, peak_equity=equity,
    )
    if not verdict.ok:
        return {"action": "blocked", "stage": "risk", "reason": verdict.reason}

    decision = await ComplianceGuard(user.id, cfg).check(
        signal=signal, kill_switch=cfg_row.kill_switch_active,
        auto_trading=cfg_row.auto_trading_enabled,
    )
    if not decision.allowed:
        return {"action": "blocked", "stage": "compliance", "reason": decision.reason}

    if cfg.automation.manual_confirmation:
        await engine._queue_pending(plan, signal)
        return {"action": "pending", "plan": asdict(plan)}

    return await engine.execute_plan(plan, signal.confidence, signal.components)
