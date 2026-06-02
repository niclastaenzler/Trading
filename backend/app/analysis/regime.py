"""Market regime & structure features — no-lookahead, scalar-at-last-bar helpers.

These quantify *context* the raw indicators miss:
  * trend strength via Kaufman's Efficiency Ratio (signal vs. noise),
  * regime label (trend vs. range),
  * where current volatility sits in its own recent distribution (percentile),
  * simple market structure (higher-highs / lower-lows, breakout state).

Everything is backward-looking; the `latest_*` helpers return a single value
computed only from data up to and including the last bar.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.analysis import indicators


def efficiency_ratio(close: pd.Series, period: int = 20) -> pd.Series:
    """Kaufman Efficiency Ratio in [0, 1]: 1 = pure trend, ~0 = pure noise."""
    change = (close - close.shift(period)).abs()
    volatility = close.diff().abs().rolling(period).sum()
    return (change / volatility.replace(0, np.nan)).fillna(0.0).clip(0, 1)


def latest_trend_strength(df: pd.DataFrame, period: int = 20) -> float:
    return float(efficiency_ratio(df["close"], period).iloc[-1])


def latest_regime(df: pd.DataFrame, period: int = 20, threshold: float = 0.4) -> str:
    return "trend" if latest_trend_strength(df, period) >= threshold else "range"


def latest_volatility_percentile(df: pd.DataFrame, atr_len: int = 14, lookback: int = 100) -> float:
    """Percentile rank (0..1) of the current ATR/price within its recent window."""
    vr = (indicators.atr(df, atr_len) / df["close"]).dropna()
    window = vr.tail(lookback)
    if len(window) < 5:
        return 0.5
    return float((window <= window.iloc[-1]).mean())


def latest_structure(df: pd.DataFrame, lookback: int = 20) -> dict:
    """Higher-highs / lower-lows over the recent window (excluding the last bar)."""
    if len(df) < lookback + 2:
        return {"higher_high": False, "lower_low": False}
    prior = df.iloc[-(lookback + 1) : -1]
    last = df.iloc[-1]
    return {
        "higher_high": bool(last["high"] > prior["high"].max()),
        "lower_low": bool(last["low"] < prior["low"].min()),
    }


def regime_features(df: pd.DataFrame) -> dict:
    """Bundle the regime/structure context for the latest bar."""
    return {
        "trend_strength": round(latest_trend_strength(df), 4),
        "regime": latest_regime(df),
        "volatility_percentile": round(latest_volatility_percentile(df), 4),
        **latest_structure(df),
    }
