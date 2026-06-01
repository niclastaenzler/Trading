"""Technical indicators implemented with pandas/numpy.

Vectorised, dependency-light (no TA-Lib system build required). Each function
takes a price series / OHLCV DataFrame and returns a pandas Series aligned to
the input index.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    # Wilder's smoothing.
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(100.0)  # no losses -> max strength


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame(
        {"macd": macd_line, "signal": signal_line, "hist": hist}
    )


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range. `df` needs high/low/close columns."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def compute_all(df: pd.DataFrame, params) -> pd.DataFrame:
    """Attach the standard indicator set to an OHLCV DataFrame.

    `params` is an `IndicatorParams`-like object (duck-typed attributes).
    """
    out = df.copy()
    out["ema_fast"] = ema(df["close"], params.ema_fast)
    out["ema_slow"] = ema(df["close"], params.ema_slow)
    out["rsi"] = rsi(df["close"], params.rsi_length)
    macd_df = macd(df["close"], params.macd_fast, params.macd_slow, params.macd_signal)
    out = out.join(macd_df)
    out["atr"] = atr(df, params.atr_length)
    return out
