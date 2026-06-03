"""Risk manager — position sizing, stop/target calculation, pre-trade validation.

MANDATORY guarantees:
  * Every trade has a stop loss (else it is rejected).
  * Position size is derived from risk-per-trade %, never arbitrary.
  * Daily loss limit and max drawdown cut trading off.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.config_defaults import StopLossType, TradingConfigModel
from app.services.signal_engine import Signal


@dataclass
class TradePlan:
    symbol: str
    side: str  # BUY | SELL
    quantity: float
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_amount: float


@dataclass
class ValidationResult:
    ok: bool
    reason: str = ""


class RiskManager:
    def __init__(self, config: TradingConfigModel) -> None:
        self.cfg = config

    # --- stop / target ---
    def _stop_distance(self, signal: Signal) -> float:
        risk = self.cfg.risk
        if risk.stop_loss_type == StopLossType.atr:
            return max(signal.atr * risk.stop_loss_value, 1e-9)
        # percent of price
        return max(signal.price * risk.stop_loss_value / 100.0, 1e-9)

    def _confidence_factor(self, signal: Signal) -> float:
        """Scale 0.4..1.0 with model confidence so stronger setups risk more of
        the (already capped) per-trade budget. Returns 1.0 when disabled."""
        if not self.cfg.risk.confidence_scaled_sizing:
            return 1.0
        # Map confidence 0.5->0.4 (min) up to 0.9+->1.0.
        return float(min(1.0, max(0.4, (signal.confidence - 0.5) / 0.4)))

    def build_plan(self, signal: Signal, equity: float) -> TradePlan:
        side = "BUY" if signal.direction > 0 else "SELL"
        stop_dist = self._stop_distance(signal)
        # Risk-per-trade budget, optionally scaled down by confidence.
        risk_amount = (
            equity * self.cfg.trading.risk_per_trade_pct / 100.0
            * self._confidence_factor(signal)
        )
        # Units sized so that hitting the stop loses exactly `risk_amount`.
        quantity = risk_amount / stop_dist

        if side == "BUY":
            stop = signal.price - stop_dist
            target = signal.price + stop_dist * self.cfg.risk.take_profit_rr
        else:
            stop = signal.price + stop_dist
            target = signal.price - stop_dist * self.cfg.risk.take_profit_rr

        return TradePlan(
            symbol=signal.symbol,
            side=side,
            quantity=round(quantity, 6),
            entry_price=signal.price,
            stop_loss=round(stop, 6),
            take_profit=round(target, 6),
            risk_amount=round(risk_amount, 2),
        )

    # --- validation ---
    def validate(
        self,
        plan: TradePlan,
        *,
        open_positions: int,
        equity: float,
        realized_pnl_today: float,
        peak_equity: float,
    ) -> ValidationResult:
        if self.cfg.risk.require_stop_loss and not plan.stop_loss:
            return ValidationResult(False, "missing stop loss")
        if plan.quantity <= 0:
            return ValidationResult(False, "non-positive position size")
        if open_positions >= self.cfg.trading.max_open_positions:
            return ValidationResult(False, "max open positions reached")

        # Daily loss limit (realized_pnl_today is negative when losing).
        if self.cfg.risk.daily_loss_limit_enabled:
            daily_limit = -equity * self.cfg.risk.daily_loss_limit_pct / 100.0
            if realized_pnl_today <= daily_limit:
                return ValidationResult(False, "daily loss limit hit")

        # Max drawdown from peak equity.
        if self.cfg.risk.max_drawdown_enabled and peak_equity > 0:
            drawdown = (peak_equity - equity) / peak_equity * 100.0
            if drawdown >= self.cfg.risk.max_drawdown_pct:
                return ValidationResult(False, "max drawdown protection")

        # Sanity: stop must be on the correct side of entry.
        if plan.side == "BUY" and plan.stop_loss >= plan.entry_price:
            return ValidationResult(False, "buy stop above entry")
        if plan.side == "SELL" and plan.stop_loss <= plan.entry_price:
            return ValidationResult(False, "sell stop below entry")

        return ValidationResult(True)
