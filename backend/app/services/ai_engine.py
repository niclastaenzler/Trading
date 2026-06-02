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

    @staticmethod
    def _labelled(df: pd.DataFrame):
        feat = build_features(df)
        future_ret = df["close"].shift(-1) / df["close"] - 1
        label = (future_ret > 0).astype(int)
        mask = future_ret.notna()
        return feat[mask][FEATURES], label[mask]

    @staticmethod
    def _new_estimator():
        return GradientBoostingClassifier(
            n_estimators=120, max_depth=3, learning_rate=0.05, random_state=42
        )

    # --- training ---
    def train(self, df: pd.DataFrame, test_fraction: float = 0.2) -> dict:
        """Fit on a chronological train split and report OUT-OF-SAMPLE accuracy.

        A chronological (not random) split prevents look-ahead leakage. The
        out-of-sample score is the honest estimate of generalisation.
        """
        if not _SKLEARN:
            raise RuntimeError("scikit-learn not installed; cannot train.")
        X, y = self._labelled(df)
        split = int(len(X) * (1 - test_fraction))
        X_train, X_test = X.iloc[:split], X.iloc[split:]
        y_train, y_test = y.iloc[:split], y.iloc[split:]

        model = self._new_estimator()
        model.fit(X_train, y_train)
        os.makedirs(os.path.dirname(MODEL_PATH) or ".", exist_ok=True)
        joblib.dump(model, MODEL_PATH)
        self._model = model
        return {
            "trained_on": int(len(X_train)),
            "tested_on": int(len(X_test)),
            "train_score": float(model.score(X_train, y_train)),
            "test_score": (
                float(model.score(X_test, y_test)) if len(X_test) else None
            ),
        }

    def walk_forward(self, df: pd.DataFrame, folds: int = 5) -> dict:
        """Expanding-window walk-forward validation.

        Splits the history into `folds` sequential test blocks; for each block,
        train on everything before it and score on the block. Reports the mean
        out-of-sample accuracy — a realistic view of live performance.
        """
        if not _SKLEARN:
            raise RuntimeError("scikit-learn not installed; cannot evaluate.")
        X, y = self._labelled(df)
        n = len(X)
        fold_size = n // (folds + 1)
        scores = []
        for k in range(1, folds + 1):
            train_end = fold_size * k
            test_end = min(fold_size * (k + 1), n)
            if test_end - train_end < 5:
                continue
            model = self._new_estimator()
            model.fit(X.iloc[:train_end], y.iloc[:train_end])
            scores.append(float(model.score(X.iloc[train_end:test_end], y.iloc[train_end:test_end])))
        mean = float(sum(scores) / len(scores)) if scores else None
        return {"folds": len(scores), "fold_scores": [round(s, 3) for s in scores],
                "mean_oos_score": round(mean, 3) if mean is not None else None}

    def train_pooled(self, enriched_frames: list[pd.DataFrame], test_fraction: float = 0.2) -> dict:
        """Train ONE model on features pooled across many instruments (a basic
        cross-sectional / multi-asset model). Each frame is an indicator-enriched
        OHLCV DataFrame. Returns metrics + feature importance."""
        if not _SKLEARN:
            raise RuntimeError("scikit-learn not installed; cannot train.")
        xs, ys = [], []
        for df in enriched_frames:
            if df is None or len(df) < 60:
                continue
            X, y = self._labelled(df)
            if len(X):
                xs.append(X)
                ys.append(y)
        if not xs:
            raise RuntimeError("no usable training data")
        X = pd.concat(xs, ignore_index=True)
        y = pd.concat(ys, ignore_index=True)
        split = int(len(X) * (1 - test_fraction))
        model = self._new_estimator()
        model.fit(X.iloc[:split], y.iloc[:split])
        os.makedirs(os.path.dirname(MODEL_PATH) or ".", exist_ok=True)
        joblib.dump(model, MODEL_PATH)
        self._model = model
        test_score = (
            float(model.score(X.iloc[split:], y.iloc[split:])) if split < len(X) else None
        )
        return {
            "instruments": len(xs),
            "trained_on": int(split),
            "tested_on": int(len(X) - split),
            "train_score": round(float(model.score(X.iloc[:split], y.iloc[:split])), 4),
            "test_score": round(test_score, 4) if test_score is not None else None,
            "feature_importance": self.feature_importance(),
        }

    def feature_importance(self) -> list[dict]:
        imp = getattr(self._model, "feature_importances_", None)
        if imp is None:
            return []
        pairs = sorted(zip(FEATURES, imp), key=lambda kv: kv[1], reverse=True)
        return [{"feature": f, "importance": round(float(v), 4)} for f, v in pairs]

    def dumps(self) -> bytes | None:
        """Serialise the fitted model to bytes (for DB persistence)."""
        if self._model is None:
            return None
        import io
        buf = io.BytesIO()
        joblib.dump(self._model, buf)
        return buf.getvalue()

    def loads(self, data: bytes) -> bool:
        """Load a model from bytes (e.g. from the DB at startup)."""
        try:
            import io
            self._model = joblib.load(io.BytesIO(data))
            return True
        except Exception:
            return False

    @property
    def is_trained(self) -> bool:
        return self._model is not None

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
