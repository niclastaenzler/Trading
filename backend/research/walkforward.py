"""Walk-forward validation (NO random split).

Expanding-window scheme: the data is cut into sequential test blocks; for each
block the model trains on everything *before* it (minus an embargo gap) and
predicts the block. This mirrors live trading — you only ever know the past —
and the concatenated test predictions are genuinely out-of-sample.

The embargo (default = feature MAX_WINDOW) prevents a training row's
backward-looking rolling window from overlapping the test period.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from research.features import MAX_WINDOW


@dataclass
class WalkForwardResult:
    proba_up: pd.Series      # OOS P(up), indexed by timestamp
    ret_next: pd.Series      # realised next-bar return for those timestamps
    y_true: pd.Series        # realised direction (1/0)
    fold_ids: pd.Series      # which fold each prediction came from
    n_folds: int


def walk_forward(
    X: pd.DataFrame,
    y: pd.Series,
    ret_next: pd.Series,
    model_factory,
    n_splits: int = 8,
    embargo: int | None = None,
    min_train: int = 150,
) -> WalkForwardResult:
    embargo = MAX_WINDOW if embargo is None else embargo
    n = len(X)
    block = n // (n_splits + 1)
    if block <= 0:
        raise ValueError("series too short for the requested number of splits")

    probs, idxs, folds = [], [], []
    fold_no = 0
    for k in range(1, n_splits + 1):
        test_start = k * block
        test_end = n if k == n_splits else (k + 1) * block
        train_end = test_start - embargo
        if train_end < min_train:
            continue
        fold_no += 1

        X_train, y_train = X.iloc[:train_end], y.iloc[:train_end]
        X_test = X.iloc[test_start:test_end]
        model = model_factory().fit(X_train, y_train)
        p = model.predict_proba_up(X_test)

        probs.append(pd.Series(p, index=X_test.index))
        idxs.append(X_test.index)
        folds.append(pd.Series(fold_no, index=X_test.index))

    if not probs:
        raise ValueError("no valid folds — increase data length or lower min_train")

    proba_up = pd.concat(probs)
    fold_ids = pd.concat(folds)
    oos_index = proba_up.index
    return WalkForwardResult(
        proba_up=proba_up,
        ret_next=ret_next.loc[oos_index],
        y_true=y.loc[oos_index],
        fold_ids=fold_ids,
        n_folds=fold_no,
    )
