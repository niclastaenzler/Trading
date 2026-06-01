from app.services.config_defaults import TradingConfigModel
from app.services.risk_manager import RiskManager
from app.services.signal_engine import Signal


def _signal(direction=1, price=100.0, atr=2.0):
    return Signal("EURUSD", direction, 0.8, price, atr, {})


def test_position_size_matches_risk():
    cfg = TradingConfigModel(trading={"risk_per_trade_pct": 1.0})
    rm = RiskManager(cfg)
    plan = rm.build_plan(_signal(), equity=10_000)
    # risk amount = 100; stop distance = atr * 1.5 = 3 -> qty ~ 33.33
    loss_at_stop = abs(plan.entry_price - plan.stop_loss) * plan.quantity
    assert abs(loss_at_stop - plan.risk_amount) < 1e-6
    assert abs(plan.risk_amount - 100.0) < 1e-6


def test_buy_stop_below_entry_and_target_above():
    rm = RiskManager(TradingConfigModel())
    plan = rm.build_plan(_signal(direction=1), 10_000)
    assert plan.stop_loss < plan.entry_price < plan.take_profit


def test_validation_blocks_daily_loss():
    cfg = TradingConfigModel(risk={"daily_loss_limit_pct": 3.0})
    rm = RiskManager(cfg)
    plan = rm.build_plan(_signal(), 10_000)
    res = rm.validate(
        plan, open_positions=0, equity=10_000,
        realized_pnl_today=-400, peak_equity=10_000,
    )
    assert not res.ok and "daily loss" in res.reason


def test_validation_blocks_max_positions():
    cfg = TradingConfigModel(trading={"max_open_positions": 2})
    rm = RiskManager(cfg)
    plan = rm.build_plan(_signal(), 10_000)
    res = rm.validate(
        plan, open_positions=2, equity=10_000,
        realized_pnl_today=0, peak_equity=10_000,
    )
    assert not res.ok and "open positions" in res.reason


def test_validation_blocks_drawdown():
    cfg = TradingConfigModel(risk={"max_drawdown_pct": 10})
    rm = RiskManager(cfg)
    plan = rm.build_plan(_signal(), 8_000)
    res = rm.validate(
        plan, open_positions=0, equity=8_000,
        realized_pnl_today=0, peak_equity=10_000,
    )
    assert not res.ok and "drawdown" in res.reason
