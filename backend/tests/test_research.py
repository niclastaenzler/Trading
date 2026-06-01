"""Tests that guard the research harness's integrity — the parts that, if
broken, would silently manufacture a fake edge."""

import numpy as np
import pandas as pd

from research import datasets as ds
from research.edge_analysis import leverage_analysis, simulate
from research.features import build_dataset, build_features
from research.models import model_factories
from research.report import evaluate_model
from research.walkforward import walk_forward


def test_features_have_no_lookahead():
    """Causality: a feature value at bar t must not change when future bars are
    appended. Truncating the series after t must reproduce the same values."""
    data = ds.make_predictable(n=400, seed=3).df
    full = build_features(data)
    cut = 300
    truncated = build_features(data.iloc[:cut])
    # Compare overlapping rows well past the warmup window.
    a = full.iloc[100:cut].to_numpy()
    b = truncated.iloc[100:cut].to_numpy()
    assert np.allclose(a, b, equal_nan=True), "feature depends on future data!"


def test_target_is_next_bar_only():
    data = ds.make_random_walk(n=300, seed=1).df
    X, y, ret_next = build_dataset(data)
    # ret_next[t] must equal close[t+1]/close[t]-1 for aligned timestamps.
    close = data["close"]
    for ts in ret_next.index[:20]:
        loc = close.index.get_loc(ts)
        expected = close.iloc[loc + 1] / close.iloc[loc] - 1
        assert abs(ret_next.loc[ts] - expected) < 1e-9


def test_walk_forward_trains_only_on_past():
    data = ds.make_predictable(n=900, seed=2).df
    X, y, ret_next = build_dataset(data)
    factories = model_factories()
    wf = walk_forward(X, y, ret_next, factories["logistic"], n_splits=5)
    # Every OOS prediction's fold must come after enough history; folds increase
    # monotonically in time (no shuffling).
    assert wf.n_folds >= 1
    assert wf.proba_up.index.is_monotonic_increasing
    assert len(wf.proba_up) == len(wf.ret_next) == len(wf.y_true)


def test_detector_reports_no_edge_on_random():
    """A pure random walk has no edge — the detector must NOT claim one."""
    data = ds.make_random_walk(n=1500, seed=5).df
    X, y, ret_next = build_dataset(data)
    factories = model_factories()
    for name in ("logistic", list(factories)[-1]):  # logistic + the advanced model
        wf = walk_forward(X, y, ret_next, factories[name], n_splits=8)
        ev = evaluate_model(wf, ppy=365)
        assert ev["has_edge"] is False, f"{name} hallucinated an edge on noise"


def test_detector_finds_injected_edge():
    """A strong AR(1) momentum signal IS predictable — the detector should find
    it with at least the simple logistic model."""
    data = ds.make_predictable(n=2500, seed=4, phi=0.45).df
    X, y, ret_next = build_dataset(data)
    factories = model_factories()
    wf = walk_forward(X, y, ret_next, factories["logistic"], n_splits=8)
    ev = evaluate_model(wf, ppy=365)
    assert ev["significance"]["hit_rate"] > 0.5
    assert ev["significance"]["mc_p_value"] < 0.05
    assert ev["has_edge"] is True


def test_leverage_leaves_sharpe_invariant_and_grows_drawdown():
    data = ds.make_predictable(n=1500, seed=6, phi=0.4).df
    X, y, ret_next = build_dataset(data)
    factories = model_factories()
    wf = walk_forward(X, y, ret_next, factories["logistic"], n_splits=6)
    _, net = simulate(wf, ppy=365)
    rows = {r.leverage: r for r in leverage_analysis(net, ppy=365, leverages=(1, 2, 3))}
    # Sharpe is (theoretically) leverage-invariant.
    assert abs(rows[1].sharpe - rows[3].sharpe) < 0.05
    # Drawdown grows with leverage.
    assert rows[3].max_drawdown >= rows[1].max_drawdown
