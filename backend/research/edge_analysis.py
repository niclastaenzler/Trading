"""Edge analysis: realistic trading simulation, metrics, significance, leverage.

Honesty principles baked in:
  * Costs are charged on every position change (turnover * cost_bps).
  * Significance is tested three ways: binomial on hit-rate, t-test on returns,
    and a Monte-Carlo vs random positions (the decisive 'beat random' test).
  * A buy & hold benchmark is always reported for context.
  * Leverage notes that Sharpe is invariant to leverage; only drawdown / ruin
    risk grow — superlinearly under compounding (volatility drag).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

try:
    from scipy import stats as _stats
    _HAS_SCIPY = True
except Exception:
    _HAS_SCIPY = False

from research.walkforward import WalkForwardResult


def positions_from_proba(proba: pd.Series, threshold: float = 0.0, long_only: bool = False) -> pd.Series:
    """Map P(up) to {-1, 0, +1}. threshold is the band around 0.5 (0 = always trade)."""
    upper, lower = 0.5 + threshold, 0.5 - threshold
    pos = pd.Series(0, index=proba.index, dtype=float)
    pos[proba > upper] = 1.0
    if not long_only:
        pos[proba < lower] = -1.0
    return pos


def _max_drawdown(equity: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity)
    return float(np.max((peak - equity) / peak)) if len(equity) else 0.0


@dataclass
class Metrics:
    n: int
    n_trades: int
    hit_rate: float
    ann_return: float
    ann_vol: float
    sharpe: float
    max_drawdown: float
    total_return: float


def compute_metrics(net_ret: pd.Series, pos: pd.Series, ret_next: pd.Series, ppy: int) -> Metrics:
    traded = pos != 0
    correct = (np.sign(pos[traded]) == np.sign(ret_next[traded]))
    hit = float(correct.mean()) if traded.any() else 0.0
    equity = np.cumprod(1 + net_ret.to_numpy())
    total = float(equity[-1] - 1) if len(equity) else 0.0
    n = len(net_ret)
    ann_ret = float((1 + total) ** (ppy / n) - 1) if n > 0 and total > -1 else -1.0
    ann_vol = float(net_ret.std() * np.sqrt(ppy))
    sharpe = float(net_ret.mean() / net_ret.std() * np.sqrt(ppy)) if net_ret.std() > 0 else 0.0
    n_trades = int((pos.diff().fillna(pos).abs() > 0).sum())
    return Metrics(n, n_trades, round(hit, 4), round(ann_ret, 4), round(ann_vol, 4),
                   round(sharpe, 3), round(_max_drawdown(equity), 4), round(total, 4))


def simulate(wf: WalkForwardResult, ppy: int, threshold: float = 0.0,
             cost_bps: float = 2.0, long_only: bool = False):
    """Run the trading simulation on out-of-sample predictions."""
    pos = positions_from_proba(wf.proba_up, threshold, long_only)
    gross = pos * wf.ret_next
    turnover = pos.diff().fillna(pos).abs()
    net = gross - turnover * cost_bps * 1e-4
    return pos, net


@dataclass
class Significance:
    hit_rate: float
    binom_p: float          # P(hit-rate this high | true rate 0.5)
    return_t_p: float       # one-sided t-test: mean strategy return > 0
    mc_p_value: float       # fraction of random strategies with Sharpe >= ours
    mc_random_sharpe_mean: float


def significance(net: pd.Series, pos: pd.Series, ret_next: pd.Series, ppy: int,
                 n_mc: int = 2000, seed: int = 7) -> Significance:
    traded = pos != 0
    n_traded = int(traded.sum())
    hits = int((np.sign(pos[traded]) == np.sign(ret_next[traded])).sum())
    hit_rate = hits / n_traded if n_traded else 0.0

    # Binomial test (one-sided) on directional accuracy.
    if _HAS_SCIPY and n_traded:
        binom_p = float(_stats.binomtest(hits, n_traded, 0.5, alternative="greater").pvalue)
    elif n_traded:
        z = (hits - 0.5 * n_traded) / np.sqrt(0.25 * n_traded)
        binom_p = float(0.5 * math.erfc(z / np.sqrt(2)))
    else:
        binom_p = 1.0

    # One-sided t-test on per-bar strategy returns.
    traded_ret = net[traded]
    if _HAS_SCIPY and len(traded_ret) > 2 and traded_ret.std() > 0:
        t = _stats.ttest_1samp(traded_ret, 0.0)
        return_t_p = float(t.pvalue / 2 if t.statistic > 0 else 1 - t.pvalue / 2)
    else:
        return_t_p = 1.0

    # Monte-Carlo vs random: keep returns fixed, randomise positions with the
    # same long/short/flat frequencies; how often does randomness match us?
    strat_sharpe = net.mean() / net.std() * np.sqrt(ppy) if net.std() > 0 else 0.0
    rng = np.random.default_rng(seed)
    freqs = pos.value_counts(normalize=True)
    choices = freqs.index.to_numpy()
    probs = freqs.to_numpy()
    r = ret_next.to_numpy()
    rand_sharpes = np.empty(n_mc)
    for i in range(n_mc):
        rp = rng.choice(choices, size=len(r), p=probs)
        rnet = rp * r
        sd = rnet.std()
        rand_sharpes[i] = (rnet.mean() / sd * np.sqrt(ppy)) if sd > 0 else 0.0
    mc_p = float((rand_sharpes >= strat_sharpe).mean())

    return Significance(round(hit_rate, 4), round(binom_p, 4), round(return_t_p, 4),
                        round(mc_p, 4), round(float(rand_sharpes.mean()), 3))


def fold_consistency(wf: WalkForwardResult, net: pd.Series) -> dict:
    """Share of walk-forward folds with positive net mean return."""
    by_fold = net.groupby(wf.fold_ids)
    means = by_fold.mean()
    positive = float((means > 0).mean())
    return {"folds": int(len(means)), "positive_fold_share": round(positive, 3),
            "fold_mean_returns": [round(float(m), 6) for m in means]}


def buy_and_hold(ret_next: pd.Series, ppy: int) -> Metrics:
    pos = pd.Series(1.0, index=ret_next.index)
    net = pos * ret_next
    return compute_metrics(net, pos, ret_next, ppy)


@dataclass
class LeverageRow:
    leverage: float
    ann_return: float
    ann_vol: float
    sharpe: float
    max_drawdown: float
    ruin: bool   # equity hit <= 0 at some point (margin wipeout)


def leverage_analysis(net: pd.Series, ppy: int, leverages=(1, 2, 3)) -> list[LeverageRow]:
    rows = []
    for L in leverages:
        lev = L * net.to_numpy()
        # Ruin: a single bar worse than -1/L wipes the account under compounding.
        gross = 1 + lev
        ruin = bool(np.any(gross <= 0))
        equity = np.cumprod(np.clip(gross, 0, None))
        total = equity[-1] - 1
        n = len(lev)
        ann_ret = float((max(equity[-1], 0)) ** (ppy / n) - 1) if n > 0 else -1.0
        ann_vol = float(np.std(lev) * np.sqrt(ppy))
        sharpe = float(np.mean(lev) / np.std(lev) * np.sqrt(ppy)) if np.std(lev) > 0 else 0.0
        rows.append(LeverageRow(float(L), round(ann_ret, 4), round(ann_vol, 4),
                                round(sharpe, 3), round(_max_drawdown(equity), 4), ruin))
    return rows
