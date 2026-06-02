"""On-demand edge evaluation for a single instrument.

Runs the same walk-forward + significance machinery as the offline research
harness, plus feature importance, and returns an HONEST verdict (edge yes/no)
with concrete next steps. Used by the live platform's `/api/research/edge`.
"""

from __future__ import annotations

import pandas as pd

from research.features import build_dataset
from research.models import GradientBoostingModel, model_factories
from research.report import evaluate_model
from research.walkforward import walk_forward


def _recommendations(ev: dict, n_samples: int) -> list[str]:
    recs: list[str] = []
    if n_samples < 800:
        recs.append("Mehr Daten: <800 Samples sind zu wenig für eine robuste Aussage "
                    "(mehr History / kürzere Timeframes / mehr Assets).")
    sig = ev["significance"]
    if sig["hit_rate"] <= 0.52:
        recs.append("Trefferquote nahe 50 % — bessere Features (Marktstruktur, "
                    "Regime, exogene Daten wie News/Funding) oder ein anderes Target "
                    "(vol-skaliert, Multi-Bar, cross-sektional).")
    if sig["mc_p_value"] >= 0.05:
        recs.append("Schlägt den Zufall nicht (MC p≥0,05) — Strategie/Features "
                    "überdenken statt Parameter zu tunen.")
    if ev["metrics"]["sharpe"] <= ev["buy_and_hold"]["sharpe"]:
        recs.append("Schlägt Buy & Hold nicht — auf Märkte/Regime fokussieren, in "
                    "denen ein echter Vorteil messbar ist.")
    if not ev["consistency"]["positive_fold_share"] >= 0.6:
        recs.append("Inkonsistent über die Walk-Forward-Folds — Edge ist instabil; "
                    "Regime-Konditionierung prüfen.")
    if not recs:
        recs.append("Edge wirkt stabil — vorsichtig live testen (Demo), klein "
                    "starten, weiter überwachen.")
    return recs


def evaluate_symbol(df: pd.DataFrame, ppy: int = 252, n_splits: int = 6) -> dict:
    """Return an honest edge report for one symbol's OHLCV history."""
    X, y, ret_next = build_dataset(df)
    if len(X) < 200:
        return {
            "ok": False,
            "reason": "zu wenig Daten für eine Bewertung",
            "n_samples": int(len(X)),
        }

    factories = model_factories()
    advanced = factories.get("xgboost") or factories.get("gboost")
    # Logistic = fast, robust baseline for the walk-forward verdict.
    wf = walk_forward(X, y, ret_next, factories["logistic"], n_splits=n_splits)
    ev = evaluate_model(wf, ppy=ppy)

    # Feature importance from a gradient-boosting fit on the whole sample
    # (explainability — which features carry signal).
    importances: list[dict] = []
    try:
        gb = GradientBoostingModel()
        gb.fit(X, y)
        clf = gb.clf
        imp = getattr(clf, "feature_importances_", None)
        if imp is not None:
            pairs = sorted(zip(X.columns, imp), key=lambda kv: kv[1], reverse=True)
            importances = [{"feature": f, "importance": round(float(v), 4)} for f, v in pairs[:8]]
    except Exception:
        importances = []

    return {
        "ok": True,
        "n_samples": int(len(X)),
        "has_edge": ev["has_edge"],
        "verdict": "EDGE VORHANDEN" if ev["has_edge"] else "KEINE ROBUSTE EDGE",
        "metrics": ev["metrics"],
        "significance": ev["significance"],
        "consistency": ev["consistency"],
        "buy_and_hold": ev["buy_and_hold"],
        "failed_checks": ev["failed_checks"],
        "feature_importance": importances,
        "recommendations": _recommendations(ev, len(X)),
    }
