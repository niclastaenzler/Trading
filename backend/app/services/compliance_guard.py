"""Compliance guard — the gate every trade must pass before reaching a broker.

Responsibilities (per spec):
  * Respect API rate limits (delegates to RateLimiter).
  * Avoid HFT-like behaviour: enforce min delay between trades + cooldown.
  * Enforce max trades per hour/day.
  * Trade only within configured sessions.
  * Pause trading during high volatility (optional).
  * Honour the kill switch.
  * Log every block for auditability.

The pure decision logic lives in `evaluate()` so it is unit-testable without
Redis; `check()` gathers live state and records audit entries.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, time as dtime, timezone

from app.core.redis_client import get_redis
from app.services.config_defaults import TradingConfigModel
from app.services.rate_limiter import RateLimiter
from app.services.signal_engine import Signal


@dataclass
class ComplianceDecision:
    allowed: bool
    reason: str = "ok"


@dataclass
class TradeState:
    last_trade_ts: float  # epoch seconds, 0 if none
    trades_last_hour: int
    trades_today: int


def _within_sessions(now: datetime, windows: list) -> bool:
    if not windows:
        return True
    t = now.timetz().replace(tzinfo=None)
    for start, end in windows:
        s = dtime.fromisoformat(start)
        e = dtime.fromisoformat(end)
        if s <= e:
            if s <= t <= e:
                return True
        else:  # window wraps midnight
            if t >= s or t <= e:
                return True
    return False


def evaluate(
    cfg: TradingConfigModel,
    state: TradeState,
    *,
    now: datetime,
    signal: Signal | None = None,
    kill_switch: bool = False,
    auto_trading: bool = True,
) -> ComplianceDecision:
    """Pure compliance decision — no I/O."""
    if kill_switch:
        return ComplianceDecision(False, "kill switch active")
    if not auto_trading:
        return ComplianceDecision(False, "auto-trading disabled")

    if not _within_sessions(now, cfg.trading.session_windows_utc):
        return ComplianceDecision(False, "outside trading session")

    now_ts = now.timestamp()
    min_delay = cfg.compliance.min_seconds_between_trades
    cooldown = cfg.automation.cooldown_seconds
    gap = now_ts - state.last_trade_ts if state.last_trade_ts else float("inf")
    if gap < max(min_delay, cooldown):
        return ComplianceDecision(False, "trade cadence cooldown")

    if state.trades_last_hour >= cfg.automation.max_trades_per_hour:
        return ComplianceDecision(False, "max trades per hour reached")
    if state.trades_today >= cfg.automation.max_trades_per_day:
        return ComplianceDecision(False, "max trades per day reached")

    if (
        cfg.compliance.halt_on_high_volatility
        and signal is not None
        and signal.price > 0
    ):
        atr_ratio = signal.atr / signal.price
        if atr_ratio > cfg.compliance.high_volatility_atr_ratio:
            return ComplianceDecision(False, "high volatility halt")

    return ComplianceDecision(True, "ok")


class ComplianceGuard:
    """Stateful wrapper: Redis-backed counters + API rate limiting + audit."""

    def __init__(self, user_id: int, cfg: TradingConfigModel) -> None:
        self.user_id = user_id
        self.cfg = cfg
        self.api_limiter = RateLimiter(
            key=f"user:{user_id}:api",
            max_per_minute=cfg.compliance.max_api_requests_per_minute,
        )

    async def allow_api_call(self) -> bool:
        return await self.api_limiter.allow()

    async def _load_state(self, symbol: str) -> TradeState:
        redis = get_redis()
        # Cadence (min delay / cooldown) is tracked PER SYMBOL so one cycle can
        # build a diversified book (several markets at once); the hourly/daily
        # caps remain global to bound total churn.
        last = await redis.get(f"user:{self.user_id}:last_trade_ts:{symbol}")
        hour = await redis.get(f"user:{self.user_id}:trades_hour")
        day = await redis.get(f"user:{self.user_id}:trades_day")
        return TradeState(
            last_trade_ts=float(last) if last else 0.0,
            trades_last_hour=int(hour) if hour else 0,
            trades_today=int(day) if day else 0,
        )

    async def check(
        self,
        *,
        signal: Signal | None,
        kill_switch: bool,
        auto_trading: bool,
    ) -> ComplianceDecision:
        symbol = signal.symbol if signal is not None else "_global"
        state = await self._load_state(symbol)
        return evaluate(
            self.cfg,
            state,
            now=datetime.now(timezone.utc),
            signal=signal,
            kill_switch=kill_switch,
            auto_trading=auto_trading,
        )

    async def record_trade(self, symbol: str = "_global") -> None:
        """Update cadence counters after a trade is placed (per-symbol delay
        plus the global hourly/daily counters)."""
        redis = get_redis()
        pipe = redis.pipeline()
        pipe.set(f"user:{self.user_id}:last_trade_ts:{symbol}", time.time())
        pipe.incr(f"user:{self.user_id}:trades_hour")
        pipe.expire(f"user:{self.user_id}:trades_hour", 3600)
        pipe.incr(f"user:{self.user_id}:trades_day")
        pipe.expire(f"user:{self.user_id}:trades_day", 86400)
        await pipe.execute()
