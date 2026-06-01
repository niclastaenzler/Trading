"""Signal engine — fuse AI prediction, pattern signals and trend confirmation.

A trade is only proposed when the *combined* confidence clears the user's
threshold AND the components agree on direction. Everything is explainable: the
returned `Signal` carries the contributing parts for the audit log.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from app.analysis import indicators, patterns
from app.services.ai_engine import ai_model
from app.services.config_defaults import StrategySettings


@dataclass
class Signal:
    symbol: str
    direction: int  # +1 buy, -1 sell, 0 no-trade
    confidence: float  # 0..1
    price: float
    atr: float
    components: dict = field(default_factory=dict)

    @property
    def actionable(self) -> bool:
        return self.direction != 0


def _trend_direction(row) -> int:
    if row["ema_fast"] > row["ema_slow"]:
        return +1
    if row["ema_fast"] < row["ema_slow"]:
        return -1
    return 0


def generate_signal(symbol: str, df: pd.DataFrame, strategy: StrategySettings) -> Signal:
    """Produce a fused trading signal for the latest bar of `df` (OHLCV)."""
    enriched = indicators.compute_all(df, strategy.indicators)
    last = enriched.iloc[-1]
    price = float(last["close"])
    atr_val = float(last["atr"])

    votes: list[tuple[int, float]] = []  # (direction, weight)
    components: dict = {}

    # --- AI component ---
    if strategy.ai_model_enabled:
        pred = ai_model.predict(enriched)
        votes.append((pred.direction, pred.confidence))
        components["ai"] = {
            "direction": pred.direction,
            "confidence": pred.confidence,
            "probabilities": pred.probabilities,
        }

    # --- Pattern component ---
    if strategy.pattern_recognition_enabled:
        pat = patterns.aggregate_patterns(enriched)
        votes.append((pat.direction, pat.strength))
        components["pattern"] = {
            "name": pat.name,
            "direction": pat.direction,
            "strength": round(pat.strength, 4),
        }

    # --- Trend filter (gate, not a vote) ---
    trend = _trend_direction(last)
    components["trend"] = trend

    if not votes:
        return Signal(symbol, 0, 0.0, price, atr_val, components)

    # Weighted directional consensus.
    net = sum(d * w for d, w in votes)
    total_w = sum(w for _, w in votes) or 1.0
    direction = 1 if net > 0 else (-1 if net < 0 else 0)
    confidence = abs(net) / total_w

    # Trend filter: veto trades against the prevailing trend.
    if strategy.trend_filter_enabled and trend != 0 and direction != trend:
        components["vetoed_by_trend"] = True
        return Signal(symbol, 0, confidence, price, atr_val, components)

    # Confidence gate.
    if confidence < strategy.signal_confidence_threshold:
        components["below_threshold"] = True
        return Signal(symbol, 0, confidence, price, atr_val, components)

    return Signal(symbol, direction, round(confidence, 4), price, atr_val, components)
