"""Assemble an honest edge verdict from the analysis outputs.

A model is credited with an edge ONLY if it clears every hurdle below. This is
deliberately strict — the default stance is 'no edge' until the data proves
otherwise across multiple independent tests.
"""

from __future__ import annotations

from dataclasses import asdict

from research import edge_analysis as ea
from research.walkforward import WalkForwardResult


def evaluate_model(
    wf: WalkForwardResult,
    ppy: int,
    threshold: float = 0.0,
    cost_bps: float = 2.0,
    long_only: bool = False,
) -> dict:
    pos, net = ea.simulate(wf, ppy, threshold, cost_bps, long_only)
    metrics = ea.compute_metrics(net, pos, wf.ret_next, ppy)
    sig = ea.significance(net, pos, wf.ret_next, ppy)
    cons = ea.fold_consistency(wf, net)
    bh = ea.buy_and_hold(wf.ret_next, ppy)

    reasons = []
    checks = {
        "hit_rate_above_50": sig.hit_rate > 0.5,
        "hit_rate_significant (binom p<0.05)": sig.binom_p < 0.05,
        "positive_sharpe": metrics.sharpe > 0,
        "beats_random (MC p<0.05)": sig.mc_p_value < 0.05,
        "beats_buy_and_hold": metrics.sharpe > bh.sharpe,
        "consistent_across_folds (>=60%)": cons["positive_fold_share"] >= 0.6,
    }
    for name, ok in checks.items():
        if not ok:
            reasons.append(name)
    has_edge = all(checks.values())

    return {
        "metrics": asdict(metrics),
        "significance": asdict(sig),
        "consistency": cons,
        "buy_and_hold": asdict(bh),
        "checks": checks,
        "has_edge": has_edge,
        "failed_checks": reasons,
        "leverage": [asdict(r) for r in ea.leverage_analysis(net, ppy)] if has_edge else [],
    }


def verdict_text(name: str, ev: dict) -> str:
    m, s = ev["metrics"], ev["significance"]
    head = "✅ EDGE FOUND" if ev["has_edge"] else "❌ NO ROBUST EDGE"
    lines = [
        f"{head}  [{name}]",
        f"  hit-rate {s['hit_rate']:.3f} (binom p={s['binom_p']:.3f}) | "
        f"Sharpe {m['sharpe']:.2f} | maxDD {m['max_drawdown']:.1%} | "
        f"trades {m['n_trades']} | MC-vs-random p={s['mc_p_value']:.3f}",
    ]
    if not ev["has_edge"]:
        lines.append(f"  failed: {', '.join(ev['failed_checks'])}")
    return "\n".join(lines)
