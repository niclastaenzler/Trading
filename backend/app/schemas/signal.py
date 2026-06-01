from pydantic import BaseModel

from app.services.config_defaults import TradingConfigModel


class ConfigUpdate(BaseModel):
    """Full config replacement, validated against the safe envelope."""

    config: TradingConfigModel


class ConfigOut(BaseModel):
    config: dict
    auto_trading_enabled: bool
    kill_switch_active: bool
    version: int


class AutomationToggle(BaseModel):
    auto_trading_enabled: bool


class BacktestRequest(BaseModel):
    symbol: str = "EURUSD"
    bars: int = 500
    starting_equity: float = 10_000.0
    seed: int | None = 42


class PendingConfirm(BaseModel):
    symbol: str
    approve: bool
