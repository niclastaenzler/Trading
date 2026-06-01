import numpy as np
import pandas as pd

from app.analysis import indicators
from app.services.config_defaults import IndicatorParams
from app.services.market_data import synthetic_ohlcv


def test_ema_tracks_constant_series():
    s = pd.Series([5.0] * 50)
    assert abs(indicators.ema(s, 10).iloc[-1] - 5.0) < 1e-9


def test_rsi_bounds():
    df = synthetic_ohlcv(bars=200, seed=1)
    r = indicators.rsi(df["close"], 14)
    assert (r >= 0).all() and (r <= 100).all()


def test_rsi_all_gains_is_high():
    s = pd.Series(np.linspace(1, 100, 100))
    assert indicators.rsi(s, 14).iloc[-1] > 95


def test_macd_columns():
    df = synthetic_ohlcv(bars=100, seed=2)
    out = indicators.macd(df["close"])
    assert set(out.columns) == {"macd", "signal", "hist"}


def test_atr_positive():
    df = synthetic_ohlcv(bars=100, seed=3)
    a = indicators.atr(df, 14)
    assert (a.dropna() >= 0).all()


def test_compute_all_attaches_columns():
    df = synthetic_ohlcv(bars=120, seed=4)
    out = indicators.compute_all(df, IndicatorParams())
    for col in ("ema_fast", "ema_slow", "rsi", "macd", "signal", "hist", "atr"):
        assert col in out.columns
