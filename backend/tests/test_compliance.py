from datetime import datetime, timezone

from app.services.compliance_guard import TradeState, evaluate
from app.services.config_defaults import TradingConfigModel
from app.services.signal_engine import Signal


def _now():
    # Mid-session (12:00 UTC) so default session window is open.
    return datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _state(last_ts=0.0, hour=0, day=0):
    return TradeState(last_trade_ts=last_ts, trades_last_hour=hour, trades_today=day)


def test_kill_switch_blocks():
    d = evaluate(TradingConfigModel(), _state(), now=_now(), kill_switch=True)
    assert not d.allowed and "kill switch" in d.reason


def test_auto_trading_off_blocks():
    d = evaluate(TradingConfigModel(), _state(), now=_now(), auto_trading=False)
    assert not d.allowed


def test_outside_session_blocks():
    cfg = TradingConfigModel(trading={"session_windows_utc": [("07:00", "08:00")]})
    d = evaluate(cfg, _state(), now=_now())
    assert not d.allowed and "session" in d.reason


def test_cadence_cooldown_blocks():
    cfg = TradingConfigModel(compliance={"min_seconds_between_trades": 300})
    just_now = _now().timestamp() - 10
    d = evaluate(cfg, _state(last_ts=just_now), now=_now())
    assert not d.allowed and "cooldown" in d.reason


def test_max_trades_per_hour_blocks():
    cfg = TradingConfigModel(automation={"max_trades_per_hour": 2})
    d = evaluate(cfg, _state(hour=2), now=_now())
    assert not d.allowed and "hour" in d.reason


def test_high_volatility_blocks():
    cfg = TradingConfigModel(
        compliance={"halt_on_high_volatility": True, "high_volatility_atr_ratio": 0.02}
    )
    sig = Signal("EURUSD", 1, 0.9, price=100.0, atr=5.0, components={})  # 5% ATR
    d = evaluate(cfg, _state(), now=_now(), signal=sig)
    assert not d.allowed and "volatility" in d.reason


def test_allows_when_all_clear():
    d = evaluate(TradingConfigModel(), _state(), now=_now())
    assert d.allowed
