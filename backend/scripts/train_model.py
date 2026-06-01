"""Train (or retrain) the example AI model and persist it to models/ai_model.pkl.

Usage:
    python -m scripts.train_model            # synthetic data
    python -m scripts.train_model --bars 5000

In production, replace `synthetic_ohlcv` with real historical candles pulled
from your broker's documented market-data endpoint.
"""

from __future__ import annotations

import argparse

from app.analysis import indicators
from app.services.ai_engine import AIModel
from app.services.config_defaults import IndicatorParams
from app.services.market_data import synthetic_ohlcv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    df = synthetic_ohlcv(bars=args.bars, seed=args.seed)
    enriched = indicators.compute_all(df, IndicatorParams())
    model = AIModel()

    wf = model.walk_forward(enriched, folds=5)
    stats = model.train(enriched)
    print(
        f"Trained on {stats['trained_on']} / tested on {stats['tested_on']} samples\n"
        f"  in-sample score : {stats['train_score']:.3f}\n"
        f"  out-of-sample   : {stats['test_score']:.3f}\n"
        f"  walk-forward    : mean OOS {wf['mean_oos_score']} over {wf['folds']} folds "
        f"{wf['fold_scores']}"
    )
    print("Saved to models/ai_model.pkl")


if __name__ == "__main__":
    main()
