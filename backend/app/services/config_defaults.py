"""Canonical trading-configuration schema with CONSERVATIVE, SAFE defaults.

Design principles (per spec):
  * Defaults must be conservative and safe.
  * The system must prevent reckless configurations -> hard caps via validators.
  * `compliance_mode` enforces an extra-conservative envelope and cannot be
    silently weakened by other fields.

Everything here is plain Pydantic, so it is reused for API validation and for
the JSON stored in `TradingConfig.data`.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class AssetClass(str, Enum):
    forex = "forex"
    crypto = "crypto"
    indices = "indices"
    stocks = "stocks"


class Timeframe(str, Enum):
    m1 = "1m"
    m5 = "5m"
    m15 = "15m"
    h1 = "1h"
    h4 = "4h"
    d1 = "1d"


class StopLossType(str, Enum):
    percent = "percent"
    atr = "atr"


# ───────────────────────── Trading settings ─────────────────────────
class TradingSettings(BaseModel):
    risk_per_trade_pct: float = Field(
        0.5, ge=0.05, le=2.0, description="Risk per trade as % of equity"
    )
    max_open_positions: int = Field(3, ge=1, le=10)
    allowed_assets: list[AssetClass] = Field(default_factory=lambda: [AssetClass.forex])
    allowed_symbols: list[str] = Field(default_factory=lambda: ["EURUSD"])
    timeframes: list[Timeframe] = Field(default_factory=lambda: [Timeframe.h1])
    # Trade only inside these UTC sessions (24h format). Empty = always.
    session_windows_utc: list[tuple[str, str]] = Field(
        default_factory=lambda: [("07:00", "16:00")]
    )


# ───────────────────────── Strategy settings ─────────────────────────
class IndicatorParams(BaseModel):
    rsi_length: int = Field(14, ge=2, le=100)
    rsi_oversold: float = Field(30.0, ge=5, le=45)
    rsi_overbought: float = Field(70.0, ge=55, le=95)
    macd_fast: int = Field(12, ge=2, le=50)
    macd_slow: int = Field(26, ge=5, le=100)
    macd_signal: int = Field(9, ge=2, le=50)
    ema_fast: int = Field(20, ge=2, le=200)
    ema_slow: int = Field(50, ge=5, le=400)
    atr_length: int = Field(14, ge=2, le=100)

    @model_validator(mode="after")
    def _coherent(self) -> "IndicatorParams":
        if self.macd_fast >= self.macd_slow:
            raise ValueError("macd_fast must be < macd_slow")
        if self.ema_fast >= self.ema_slow:
            raise ValueError("ema_fast must be < ema_slow")
        if self.rsi_oversold >= self.rsi_overbought:
            raise ValueError("rsi_oversold must be < rsi_overbought")
        return self


class StrategySettings(BaseModel):
    ai_model_enabled: bool = True
    pattern_recognition_enabled: bool = True
    trend_filter_enabled: bool = True
    # News/sentiment overlay. Inactive until a news source is connected
    # (no feed = neutral, no effect). See app.services.sentiment.
    use_sentiment: bool = False
    indicators: IndicatorParams = Field(default_factory=IndicatorParams)
    # Minimum combined confidence (0-1) required before any trade.
    signal_confidence_threshold: float = Field(0.65, ge=0.5, le=0.99)


# ───────────────────────── Automation controls ─────────────────────────
class AutomationSettings(BaseModel):
    # Master switch is stored on the model row; these shape behaviour when on.
    manual_confirmation: bool = Field(
        True, description="Semi-auto: require human approval before each trade"
    )
    max_trades_per_hour: int = Field(2, ge=1, le=20)
    max_trades_per_day: int = Field(6, ge=1, le=60)
    cooldown_seconds: int = Field(300, ge=30, le=86400)


# ───────────────────────── Risk management ─────────────────────────
class RiskSettings(BaseModel):
    stop_loss_type: StopLossType = StopLossType.atr
    stop_loss_value: float = Field(1.5, gt=0, le=20, description="% or ATR multiple")
    take_profit_rr: float = Field(2.0, ge=0.5, le=10, description="Reward:risk ratio")
    trailing_stop_enabled: bool = False
    trailing_stop_value: float = Field(1.0, gt=0, le=20)
    daily_loss_limit_pct: float = Field(3.0, ge=0.5, le=10)
    max_drawdown_pct: float = Field(10.0, ge=2, le=30)
    require_stop_loss: bool = Field(True, description="Block trades without a stop")
    # Scale position size by model confidence (within the risk-per-trade budget).
    confidence_scaled_sizing: bool = True


# ───────────────────────── Edge layer ─────────────────────────
class EdgeSettings(BaseModel):
    """Selective-trading layer: trade only the genuinely attractive setups."""

    enabled: bool = True
    # Minimum combined edge score (0..1) required to act.
    min_edge_score: float = Field(0.5, ge=0, le=1)
    # Only trade in a trending regime (skip choppy/sideways markets).
    require_trend_regime: bool = True
    # Minimum trend strength (Kaufman efficiency ratio) to act.
    min_trend_strength: float = Field(0.3, ge=0, le=1)
    # Skip when current volatility sits above this percentile of its own history.
    max_volatility_percentile: float = Field(0.9, ge=0.1, le=1)


# ───────────────────────── Compliance controls ─────────────────────────
class ComplianceSettings(BaseModel):
    # When True, conservative ceilings are enforced regardless of other fields.
    compliance_mode: bool = True
    max_api_requests_per_minute: int = Field(60, ge=1, le=300)
    min_seconds_between_trades: int = Field(60, ge=10, le=3600)
    halt_on_high_volatility: bool = True
    # ATR/price ratio above which trading pauses (e.g. 0.03 = 3%).
    high_volatility_atr_ratio: float = Field(0.03, gt=0, le=0.5)
    logging_level: str = Field("full_audit")  # basic | full_audit


# ───────────────────────── Root config ─────────────────────────
class TradingConfigModel(BaseModel):
    """Complete user configuration with conservative defaults."""

    trading: TradingSettings = Field(default_factory=TradingSettings)
    strategy: StrategySettings = Field(default_factory=StrategySettings)
    automation: AutomationSettings = Field(default_factory=AutomationSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    edge: EdgeSettings = Field(default_factory=EdgeSettings)
    compliance: ComplianceSettings = Field(default_factory=ComplianceSettings)

    @model_validator(mode="after")
    def _enforce_compliance_envelope(self) -> "TradingConfigModel":
        """Hard guardrails. In compliance mode we clamp anything reckless."""
        if self.compliance.compliance_mode:
            # Cap risk and rate, enforce stops + safe cadence.
            self.trading.risk_per_trade_pct = min(self.trading.risk_per_trade_pct, 1.0)
            self.trading.max_open_positions = min(self.trading.max_open_positions, 5)
            self.automation.max_trades_per_hour = min(
                self.automation.max_trades_per_hour, 6
            )
            self.automation.max_trades_per_day = min(
                self.automation.max_trades_per_day, 20
            )
            self.compliance.max_api_requests_per_minute = min(
                self.compliance.max_api_requests_per_minute, 120
            )
            self.compliance.min_seconds_between_trades = max(
                self.compliance.min_seconds_between_trades, 30
            )
            self.risk.require_stop_loss = True
            self.risk.daily_loss_limit_pct = min(self.risk.daily_loss_limit_pct, 5.0)

        # Independent of compliance mode: a stop loss is mandatory by design.
        if not self.risk.require_stop_loss:
            raise ValueError(
                "require_stop_loss cannot be disabled — stops are mandatory."
            )

        # Cooldown must never undercut the compliance min-delay.
        self.automation.cooldown_seconds = max(
            self.automation.cooldown_seconds,
            self.compliance.min_seconds_between_trades,
        )
        return self


def default_config() -> TradingConfigModel:
    return TradingConfigModel()
