"""Signal engine — fuse AI prediction, pattern signals, trend confirmation, and
an Edge Layer that only lets through genuinely attractive setups.

Pipeline per bar:
  1. AI + pattern votes -> fused direction & confidence.
  2. Trend gate (don't fight the prevailing trend).
  3. Confidence gate (user threshold).
  4. Edge Layer: regime / trend-strength / volatility filters + an edge score.

Everything is explainable: the `Signal.components` dict records every part and
the reason a trade was skipped, and `edge_score` ranks setups across markets.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from app.analysis import indicators, patterns, regime
from app.services.ai_engine import ai_model
from app.services.config_defaults import EdgeSettings, StrategySettings


@dataclass
class Signal:
    symbol: str
    direction: int  # +1 buy, -1 sell, 0 no-trade
    confidence: float  # 0..1
    price: float
    atr: float
    edge_score: float = 0.0  # 0..1 ranking score (confidence + context)
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


def _apply_edge_layer(
    confidence: float, ctx: dict, edge: EdgeSettings
) -> tuple[bool, float, str]:
    """Return (passes, edge_score, reason). edge_score blends confidence with
    trend strength and a volatility penalty so the best setups rank highest."""
    ts = ctx["trend_strength"]
    volp = ctx["volatility_percentile"]
    vol_factor = max(0.0, 1.0 - volp)  # calmer markets score higher
    edge_score = round(confidence * (0.5 + 0.5 * ts) * (0.5 + 0.5 * vol_factor), 4)

    if not edge.enabled:
        return True, edge_score, ""
    if edge.require_trend_regime and ctx["regime"] != "trend":
        return False, edge_score, "Seitwärtsphase (kein Trend)"
    if ts < edge.min_trend_strength:
        return False, edge_score, "Trend zu schwach"
    if volp > edge.max_volatility_percentile:
        return False, edge_score, "Volatilität zu hoch"
    if edge_score < edge.min_edge_score:
        return False, edge_score, "Edge-Score zu niedrig"
    return True, edge_score, ""


def generate_signal(
    symbol: str,
    df: pd.DataFrame,
    strategy: StrategySettings,
    edge: EdgeSettings | None = None,
    sentiment: float = 0.0,
) -> Signal:
    """Produce a fused, edge-filtered trading signal for the latest bar.

    `sentiment` (-1..1) is an optional news-sentiment overlay; 0 = neutral/off.
    """
    enriched = indicators.compute_all(df, strategy.indicators)
    last = enriched.iloc[-1]
    price = float(last["close"])
    atr_val = float(last["atr"])

    # Market regime / structure context (no lookahead).
    ctx = regime.regime_features(df)

    votes: list[tuple[int, float]] = []
    components: dict = {"regime": ctx}

    if strategy.ai_model_enabled:
        pred = ai_model.predict(enriched)
        votes.append((pred.direction, pred.confidence))
        components["ai"] = {
            "direction": pred.direction,
            "confidence": pred.confidence,
            "probabilities": pred.probabilities,
        }

    if strategy.pattern_recognition_enabled:
        pat = patterns.aggregate_patterns(enriched)
        votes.append((pat.direction, pat.strength))
        components["pattern"] = {
            "name": pat.name, "direction": pat.direction,
            "strength": round(pat.strength, 4),
        }

    trend = _trend_direction(last)
    components["trend"] = trend

    if not votes:
        return Signal(symbol, 0, 0.0, price, atr_val, 0.0, components)

    net = sum(d * w for d, w in votes)
    total_w = sum(w for _, w in votes) or 1.0
    direction = 1 if net > 0 else (-1 if net < 0 else 0)
    confidence = round(abs(net) / total_w, 4)

    # Trend gate.
    if strategy.trend_filter_enabled and trend != 0 and direction != trend:
        components["vetoed_by_trend"] = True
        return Signal(symbol, 0, confidence, price, atr_val, 0.0, components)

    # Confidence gate.
    if confidence < strategy.signal_confidence_threshold:
        components["below_threshold"] = True
        return Signal(symbol, 0, confidence, price, atr_val, 0.0, components)

    # Edge layer: selective trading + ranking score.
    edge = edge or EdgeSettings()
    passes, edge_score, reason = _apply_edge_layer(confidence, ctx, edge)

    # News-sentiment overlay (only when a real value is present): veto trades that
    # strongly oppose the news, and tilt the edge score toward aligned sentiment.
    if strategy.use_sentiment and sentiment != 0.0:
        components["sentiment"] = round(sentiment, 4)
        if (direction > 0 and sentiment < -0.15) or (direction < 0 and sentiment > 0.15):
            passes, reason = False, "News-Sentiment gegen Trade"
        else:
            edge_score = round(min(1.0, edge_score * (1 + 0.2 * direction * sentiment)), 4)

    components["edge_score"] = edge_score
    if not passes:
        components["edge_rejected"] = reason
        return Signal(symbol, 0, confidence, price, atr_val, edge_score, components)

    return Signal(symbol, direction, confidence, price, atr_val, edge_score, components)
