"""The configuration system must prevent reckless settings."""

import pytest
from pydantic import ValidationError

from app.services.config_defaults import (
    TradingConfigModel,
    default_config,
)


def test_defaults_are_conservative():
    cfg = default_config()
    assert cfg.trading.risk_per_trade_pct <= 1.0
    assert cfg.automation.manual_confirmation is True
    assert cfg.compliance.compliance_mode is True
    assert cfg.risk.require_stop_loss is True


def test_risk_per_trade_hard_cap():
    with pytest.raises(ValidationError):
        TradingConfigModel(trading={"risk_per_trade_pct": 50})


def test_compliance_mode_clamps_risk():
    cfg = TradingConfigModel(
        trading={"risk_per_trade_pct": 2.0},
        compliance={"compliance_mode": True},
    )
    # Clamped to the 1.0% compliance ceiling.
    assert cfg.trading.risk_per_trade_pct == 1.0


def test_compliance_mode_forces_stop_loss_back_on():
    # With compliance mode on, disabling stops is silently corrected (safe).
    cfg = TradingConfigModel(
        risk={"require_stop_loss": False}, compliance={"compliance_mode": True}
    )
    assert cfg.risk.require_stop_loss is True


def test_cannot_disable_stop_loss_even_without_compliance_mode():
    # With compliance mode off, the independent guard rejects it outright.
    with pytest.raises(ValidationError):
        TradingConfigModel(
            risk={"require_stop_loss": False}, compliance={"compliance_mode": False}
        )


def test_cooldown_never_below_min_delay():
    cfg = TradingConfigModel(
        automation={"cooldown_seconds": 30},
        compliance={"min_seconds_between_trades": 120},
    )
    assert cfg.automation.cooldown_seconds >= 120


def test_incoherent_indicators_rejected():
    with pytest.raises(ValidationError):
        TradingConfigModel(strategy={"indicators": {"ema_fast": 50, "ema_slow": 20}})
