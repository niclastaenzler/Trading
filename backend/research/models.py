"""Models under a single interface: fit(X, y) and predict_proba_up(X) -> P(up).

Includes honest baselines (random, majority class, momentum persistence) so any
'advanced' model must be shown to beat naive alternatives — not just beat 50%.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:  # XGBoost is optional; fall back to sklearn gradient boosting.
    from xgboost import XGBClassifier

    _HAS_XGB = True
except Exception:
    _HAS_XGB = False


class BaseModel:
    name = "base"

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "BaseModel":
        return self

    def predict_proba_up(self, X: pd.DataFrame) -> np.ndarray:
        raise NotImplementedError


class RandomModel(BaseModel):
    name = "random"

    def __init__(self, seed: int = 0):
        self.rng = np.random.default_rng(seed)

    def predict_proba_up(self, X):
        return self.rng.random(len(X))


class MajorityClassModel(BaseModel):
    """Predicts the constant base rate of 'up' from training (≈ always-long if
    the market drifts up). The hardest naive baseline to beat on long-only."""

    name = "majority"

    def fit(self, X, y):
        self.p = float(y.mean())
        return self

    def predict_proba_up(self, X):
        return np.full(len(X), self.p)


class PersistenceModel(BaseModel):
    """Naive momentum: predict next direction = sign of the last return."""

    name = "persistence"

    def predict_proba_up(self, X):
        return (X["ret_1"].to_numpy() > 0).astype(float)


class LogisticModel(BaseModel):
    name = "logistic"

    def __init__(self):
        # Scaler fit inside the pipeline -> only on the training fold (no leak).
        self.pipe = Pipeline(
            [("scale", StandardScaler()),
             ("clf", LogisticRegression(max_iter=1000, C=1.0))]
        )

    def fit(self, X, y):
        self.pipe.fit(X, y)
        return self

    def predict_proba_up(self, X):
        return self.pipe.predict_proba(X)[:, 1]


class GradientBoostingModel(BaseModel):
    name = "xgboost" if _HAS_XGB else "gboost"

    def __init__(self):
        if _HAS_XGB:
            self.clf = XGBClassifier(
                n_estimators=200, max_depth=3, learning_rate=0.03,
                subsample=0.8, colsample_bytree=0.8, eval_metric="logloss",
                random_state=42,
            )
        else:
            self.clf = GradientBoostingClassifier(
                n_estimators=200, max_depth=3, learning_rate=0.03,
                subsample=0.8, random_state=42,
            )

    def fit(self, X, y):
        self.clf.fit(X, y)
        return self

    def predict_proba_up(self, X):
        return self.clf.predict_proba(X)[:, 1]


def model_factories() -> dict:
    """Name -> zero-arg factory, ordered baseline → advanced."""
    return {
        "random": lambda: RandomModel(seed=1),
        "majority": MajorityClassModel,
        "persistence": PersistenceModel,
        "logistic": LogisticModel,
        GradientBoostingModel().name: GradientBoostingModel,
    }
