"""AI engine — example model producing buy/sell/hold probabilities.

Inputs : OHLCV + indicator features.
Output : probability score per class and a directional confidence in [0, 1].

Two modes:
  * If a trained model artifact exists (joblib), load and use it.
  * Otherwise fall back to a transparent, deterministic heuristic so the
    platform is functional out of the box (and unit-testable without training).

`train()` fits a GradientBoostingClassifier on the sign of the next-bar return,
demonstrating an end-to-end, retrainable pipeline.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

try:  # scikit-learn is optional at runtime (heuristic fallback works without it)
    import joblib
    from sklearn.ensemble import GradientBoostingClassifier

    _SKLEARN = True
except Exception:  # pragma: no cover
    _SKLEARN = False

MODEL_PATH = os.getenv("AI_MODEL_PATH", "models/ai_model.pkl")

FEATURES = ["rsi", "macd", "hist", "ema_spread", "ret_1", "ret_5", "atr_ratio"]


@dataclass
class Prediction:
    direction: int  # +1 buy, -1 sell, 0 hold
    confidence: float  # 0..1
    probabilities: dict[str, float]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Derive model features from an indicator-enriched OHLCV frame."""
    feat = pd.DataFrame(index=df.index)
    feat["rsi"] = df["rsi"]
    feat["macd"] = df["macd"]
    feat["hist"] = df["hist"]
    feat["ema_spread"] = (df["ema_fast"] - df["ema_slow"]) / df["close"]
    feat["ret_1"] = df["close"].pct_change(1)
    feat["ret_5"] = df["close"].pct_change(5)
    feat["atr_ratio"] = df["atr"] / df["close"]
    return feat.replace([np.inf, -np.inf], np.nan).fillna(0.0)


class AIModel:
    def __init__(self) -> None:
        self._model = None
        if _SKLEARN and os.path.exists(MODEL_PATH):
            try:
                self._model = joblib.load(MODEL_PATH)
            except Exception:
                self._model = None

    # --- training ---
    def train(self, df: pd.DataFrame) -> dict:
        if not _SKLEARN:
            raise RuntimeError("scikit-learn not installed; cannot train.")
        feat = build_features(df)
        # Label: 1 if next-bar return positive, else 0.
        future_ret = df["close"].shift(-1) / df["close"] - 1
        label = (future_ret > 0).astype(int)
        mask = future_ret.notna()
        X, y = feat[mask][FEATURES], label[mask]
        model = GradientBoostingClassifier(
            n_estimators=120, max_depth=3, learning_rate=0.05, random_state=42
        )
        model.fit(X, y)
        os.makedirs(os.path.dirname(MODEL_PATH) or ".", exist_ok=True)
        joblib.dump(model, MODEL_PATH)
        self._model = model
        return {"trained_on": int(mask.sum()), "score": float(model.score(X, y))}

    # --- inference ---
    def predict(self, df: pd.DataFrame) -> Prediction:
        feat = build_features(df).iloc[[-1]][FEATURES]
        if self._model is not None:
            proba_up = float(self._model.predict_proba(feat)[0][1])
        else:
            proba_up = self._heuristic_proba(df)

        # Convert P(up) into buy/sell/hold with a neutral dead-band.
        if proba_up >= 0.5:
            direction, conf = +1, proba_up
        else:
            direction, conf = -1, 1 - proba_up

        # Dead-band -> hold when signal is weak.
        if abs(proba_up - 0.5) < 0.05:
            direction = 0

        probs = {
            "buy": round(proba_up, 4),
            "sell": round(1 - proba_up, 4),
            "hold": round(1 - abs(proba_up - 0.5) * 2, 4),
        }
        return Prediction(direction=direction, confidence=round(conf, 4), probabilities=probs)

    @staticmethod
    def _heuristic_proba(df: pd.DataFrame) -> float:
        """Transparent fallback: blend trend, momentum and RSI into P(up)."""
        row = df.iloc[-1]
        score = 0.0
        # Trend via EMA spread.
        score += np.tanh((row["ema_fast"] - row["ema_slow"]) / max(row["close"], 1e-9) * 100)
        # Momentum via MACD histogram (normalised).
        score += np.tanh(row["hist"] / max(abs(df["hist"]).mean(), 1e-9))
        # Mean-reversion via RSI distance from 50.
        score += (50 - row["rsi"]) / 50.0 * 0.5
        # Squash to a probability around 0.5.
        return float(1 / (1 + np.exp(-score)))


# Module-level singleton (lazy-loaded artifact).
ai_model = AIModel()
