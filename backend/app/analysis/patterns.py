"""Price-action pattern recognition: candlesticks, support/resistance, breakouts.

Returns small, explainable signals (-1 bearish .. +1 bullish) plus a label, so
the signal engine and the audit log can reason about *why* a trade fired.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class PatternSignal:
    name: str
    direction: int  # +1 bullish, -1 bearish, 0 neutral
    strength: float  # 0..1


def _body(o: float, c: float) -> float:
    return abs(c - o)


def detect_candlestick(df: pd.DataFrame) -> PatternSignal:
    """Inspect the last two candles for common reversal patterns."""
    if len(df) < 2:
        return PatternSignal("none", 0, 0.0)

    o, h, l, c = (df["open"], df["high"], df["low"], df["close"])
    o1, h1, l1, c1 = o.iloc[-1], h.iloc[-1], l.iloc[-1], c.iloc[-1]
    o2, c2 = o.iloc[-2], c.iloc[-2]

    rng = max(h1 - l1, 1e-9)
    body = _body(o1, c1)
    upper_wick = h1 - max(o1, c1)
    lower_wick = min(o1, c1) - l1

    # Hammer (bullish): small body up top, long lower wick.
    if lower_wick > 2 * body and upper_wick < body and c1 >= o1:
        return PatternSignal("hammer", +1, min(1.0, lower_wick / rng))

    # Shooting star (bearish): small body down low, long upper wick.
    if upper_wick > 2 * body and lower_wick < body and c1 <= o1:
        return PatternSignal("shooting_star", -1, min(1.0, upper_wick / rng))

    # Bullish engulfing.
    if c2 < o2 and c1 > o1 and c1 >= o2 and o1 <= c2:
        return PatternSignal("bullish_engulfing", +1, min(1.0, body / rng))

    # Bearish engulfing.
    if c2 > o2 and c1 < o1 and o1 >= c2 and c1 <= o2:
        return PatternSignal("bearish_engulfing", -1, min(1.0, body / rng))

    return PatternSignal("none", 0, 0.0)


def support_resistance(df: pd.DataFrame, lookback: int = 50) -> tuple[float, float]:
    """Simple recent swing-low (support) and swing-high (resistance)."""
    window = df.tail(lookback)
    return float(window["low"].min()), float(window["high"].max())


def detect_breakout(df: pd.DataFrame, lookback: int = 50) -> PatternSignal:
    """Breakout above resistance / below support of the prior window."""
    if len(df) < lookback + 1:
        return PatternSignal("none", 0, 0.0)

    prior = df.iloc[-(lookback + 1) : -1]
    resistance = prior["high"].max()
    support = prior["low"].min()
    close = df["close"].iloc[-1]
    rng = max(resistance - support, 1e-9)

    if close > resistance:
        return PatternSignal("breakout_up", +1, min(1.0, (close - resistance) / rng))
    if close < support:
        return PatternSignal("breakout_down", -1, min(1.0, (support - close) / rng))
    return PatternSignal("none", 0, 0.0)


def aggregate_patterns(df: pd.DataFrame) -> PatternSignal:
    """Combine pattern detectors into a single directional signal."""
    signals = [detect_candlestick(df), detect_breakout(df)]
    score = float(np.mean([s.direction * s.strength for s in signals]))
    direction = int(np.sign(score))
    names = "+".join(s.name for s in signals if s.direction != 0) or "none"
    return PatternSignal(names, direction, min(1.0, abs(score)))
