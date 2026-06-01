"""Trading engine — orchestrates the full decision -> execution pipeline.

Pipeline per symbol/bar:
  1. signal_engine     -> fused AI + pattern + trend signal
  2. risk_manager      -> position size, stop/target, validation
  3. compliance_guard  -> rate/cadence/session/volatility/kill-switch gate
  4. broker            -> execute (paper by default; live only if opted in)
  5. persistence       -> Order + Trade rows
  6. audit + realtime  -> AuditLog, Redis pub/sub, Telegram

Semi-auto (`manual_confirmation`) queues a pending proposal instead of
executing, surfacing it for human approval via the API/WebSocket.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import SIGNAL_CHANNEL, get_redis, publish
from app.models.config import TradingConfig
from app.models.trade import Order, Trade
from app.services.audit import log_audit
from app.services.broker import get_broker
from app.services.broker.broker_interface import BrokerInterface
from app.services.compliance_guard import ComplianceGuard
from app.services.config_defaults import TradingConfigModel
from app.services.notifications import send_telegram
from app.services.risk_manager import RiskManager, TradePlan
from app.services.signal_engine import generate_signal


class TradingEngine:
    def __init__(
        self,
        db: AsyncSession,
        user_id: int,
        config_row: TradingConfig,
        broker: BrokerInterface,
    ) -> None:
        self.db = db
        self.user_id = user_id
        self.config_row = config_row
        self.cfg = TradingConfigModel(**(config_row.data or {}))
        self.broker = broker
        self.risk = RiskManager(self.cfg)
        self.compliance = ComplianceGuard(user_id, self.cfg)

    # --- account state helpers ---
    async def _peak_equity(self, equity: float) -> float:
        redis = get_redis()
        key = f"user:{self.user_id}:peak_equity"
        prev = await redis.get(key)
        peak = max(float(prev) if prev else 0.0, equity)
        await redis.set(key, peak)
        return peak

    async def _realized_pnl_today(self) -> float:
        start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        result = await self.db.execute(
            select(Trade.pnl).where(
                Trade.user_id == self.user_id,
                Trade.status == "CLOSED",
                Trade.closed_at >= start,
            )
        )
        return float(sum(p or 0.0 for p in result.scalars().all()))

    # --- main entrypoint ---
    async def process_symbol(self, symbol: str, ohlcv: pd.DataFrame) -> dict:
        """Run the pipeline for one symbol. Returns a structured outcome."""
        signal = generate_signal(symbol, ohlcv, self.cfg.strategy)

        # Keep the paper broker's price feed in sync.
        if hasattr(self.broker, "set_price"):
            self.broker.set_price(symbol, signal.price)

        await publish(
            SIGNAL_CHANNEL,
            {"user_id": self.user_id, "symbol": symbol, "signal": asdict(signal)},
        )

        if not signal.actionable:
            return {"action": "none", "symbol": symbol, "signal": asdict(signal)}

        equity = await self.broker.get_balance()
        plan = self.risk.build_plan(signal, equity)

        # Risk validation.
        open_positions = len(await self.broker.get_positions())
        peak = await self._peak_equity(equity)
        realized = await self._realized_pnl_today()
        verdict = self.risk.validate(
            plan,
            open_positions=open_positions,
            equity=equity,
            realized_pnl_today=realized,
            peak_equity=peak,
        )
        if not verdict.ok:
            await log_audit(
                self.db, event="RISK_BLOCK", user_id=self.user_id,
                message=f"risk blocked {symbol}: {verdict.reason}",
                severity="warning", context={"plan": asdict(plan)},
            )
            return {"action": "blocked", "stage": "risk", "reason": verdict.reason}

        # Compliance gate.
        decision = await self.compliance.check(
            signal=signal,
            kill_switch=self.config_row.kill_switch_active,
            auto_trading=self.config_row.auto_trading_enabled,
        )
        if not decision.allowed:
            await log_audit(
                self.db, event="COMPLIANCE_BLOCK", user_id=self.user_id,
                message=f"compliance blocked {symbol}: {decision.reason}",
                severity="warning", context={"reason": decision.reason},
            )
            return {"action": "blocked", "stage": "compliance", "reason": decision.reason}

        # Semi-auto: queue for human approval instead of executing.
        if self.cfg.automation.manual_confirmation:
            await self._queue_pending(plan, signal)
            await log_audit(
                self.db, event="SIGNAL_PENDING", user_id=self.user_id,
                message=f"pending confirmation: {plan.side} {symbol}",
                context={"plan": asdict(plan), "confidence": signal.confidence},
            )
            return {"action": "pending", "plan": asdict(plan)}

        return await self.execute_plan(plan, signal.confidence, signal.components)

    async def _queue_pending(self, plan: TradePlan, signal) -> None:
        await get_redis().set(
            f"user:{self.user_id}:pending:{plan.symbol}",
            json.dumps({"plan": asdict(plan), "confidence": signal.confidence}),
            ex=900,
        )

    # --- execution ---
    async def execute_plan(
        self, plan: TradePlan, confidence: float, components: dict | None = None
    ) -> dict:
        order = await self.broker.place_order(
            plan.symbol, plan.side, plan.quantity,
            stop_loss=plan.stop_loss, take_profit=plan.take_profit,
        )
        mode = "paper" if self.broker.is_paper else "live"

        self.db.add(
            Order(
                user_id=self.user_id, broker=self.broker.name,
                broker_order_id=order.broker_order_id, symbol=plan.symbol,
                side=plan.side, quantity=plan.quantity, price=order.price,
                stop_loss=plan.stop_loss, take_profit=plan.take_profit,
                status=order.status, mode=mode, reason=order.reason,
            )
        )

        if order.status != "FILLED":
            await log_audit(
                self.db, event="ORDER_REJECTED", user_id=self.user_id,
                message=f"order rejected {plan.symbol}: {order.reason}",
                severity="error",
            )
            return {"action": "rejected", "reason": order.reason}

        trade = Trade(
            user_id=self.user_id, symbol=plan.symbol, side=plan.side,
            quantity=plan.quantity, entry_price=order.price,
            stop_loss=plan.stop_loss, take_profit=plan.take_profit,
            status="OPEN", mode=mode, confidence=confidence, strategy="fused",
        )
        self.db.add(trade)
        await self.compliance.record_trade()
        await log_audit(
            self.db, event="ORDER_PLACED", user_id=self.user_id,
            message=f"{plan.side} {plan.quantity} {plan.symbol} @ {order.price} ({mode})",
            context={"confidence": confidence, "components": components or {}},
        )
        await publish(
            "events",
            {"type": "order_placed", "user_id": self.user_id, "symbol": plan.symbol,
             "side": plan.side, "price": order.price, "mode": mode},
        )
        await send_telegram(
            f"*Trade* {plan.side} {plan.quantity} {plan.symbol} @ {order.price}\n"
            f"SL {plan.stop_loss} / TP {plan.take_profit} (conf {confidence:.0%}, {mode})"
        )
        return {"action": "executed", "order_id": order.broker_order_id, "mode": mode}
