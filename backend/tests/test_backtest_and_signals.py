from app.backtest.engine import run_backtest
from app.services.config_defaults import TradingConfigModel
from app.services.market_data import synthetic_ohlcv
from app.services.signal_engine import generate_signal


def test_signal_generation_runs():
    df = synthetic_ohlcv(bars=200, seed=7)
    sig = generate_signal("EURUSD", df, TradingConfigModel().strategy)
    assert sig.symbol == "EURUSD"
    assert -1 <= sig.direction <= 1
    assert 0.0 <= sig.confidence <= 1.0
    assert sig.price > 0


def test_high_threshold_suppresses_trades():
    df = synthetic_ohlcv(bars=200, seed=7)
    strat = TradingConfigModel().strategy
    strat.signal_confidence_threshold = 0.99
    sig = generate_signal("EURUSD", df, strat)
    assert sig.direction == 0  # nothing clears a 99% bar


def test_edge_layer_can_block_and_scores():
    from app.services.config_defaults import EdgeSettings
    df = synthetic_ohlcv(bars=300, seed=7)
    strat = TradingConfigModel().strategy
    strat.signal_confidence_threshold = 0.5
    # An impossible edge bar (require very strong trend) should block trades.
    strict = EdgeSettings(min_trend_strength=0.99, min_edge_score=0.99)
    sig = generate_signal("EURUSD", df, strat, strict)
    assert sig.direction == 0  # edge layer vetoes
    assert "regime" in sig.components
    # edge_score is always reported for ranking.
    assert 0.0 <= sig.edge_score <= 1.0


def test_backtest_produces_metrics():
    df = synthetic_ohlcv(bars=400, seed=11)
    result = run_backtest("EURUSD", df, TradingConfigModel(), starting_equity=10_000)
    assert result.starting_equity == 10_000
    assert result.num_trades >= 0
    assert 0.0 <= result.win_rate <= 1.0
    assert len(result.equity_curve) > 0
    assert result.max_drawdown_pct >= 0
