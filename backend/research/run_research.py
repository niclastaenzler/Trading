"""CLI entrypoint: run the full edge study on a dataset and print an honest report.

Examples
--------
    # Controlled validation of the detector itself:
    python -m research.run_research --dataset random       # expect: NO edge
    python -m research.run_research --dataset predictable  # expect: EDGE

    # Real data:
    python -m research.run_research --dataset csv --csv research/data/aapl.csv
    python -m research.run_research --dataset binance --symbol BTCUSDT   # needs network
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from research import datasets as ds
from research.features import build_dataset
from research.models import model_factories
from research.report import evaluate_model, verdict_text
from research.walkforward import walk_forward

ADVANCED = {"logistic", "gboost", "xgboost"}


def load(args) -> ds.Dataset:
    d = args.dataset
    if d == "random":
        return ds.make_random_walk(seed=args.seed)
    if d == "predictable":
        return ds.make_predictable(seed=args.seed, phi=args.phi)
    if d == "csv":
        return ds.load_csv(args.csv, periods_per_year=args.ppy)
    if d == "binance":
        return ds.load_binance(symbol=args.symbol, interval=args.interval)
    if d == "yfinance":
        return ds.load_yfinance(symbol=args.symbol)
    raise SystemExit(f"unknown dataset '{d}'")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default="predictable",
                   choices=["random", "predictable", "csv", "binance", "yfinance"])
    p.add_argument("--csv"); p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--interval", default="1d"); p.add_argument("--ppy", type=int, default=252)
    p.add_argument("--phi", type=float, default=0.25); p.add_argument("--seed", type=int, default=0)
    p.add_argument("--splits", type=int, default=8); p.add_argument("--threshold", type=float, default=0.0)
    p.add_argument("--cost-bps", type=float, default=2.0); p.add_argument("--long-only", action="store_true")
    p.add_argument("--out", default="research/reports")
    args = p.parse_args()

    dataset = load(args)
    X, y, ret_next = build_dataset(dataset.df)
    ppy = dataset.periods_per_year

    print(f"\n=== Edge study: {dataset.name} ===")
    print(f"{'REAL DATA' if dataset.is_real else 'SYNTHETIC CONTROL'} | "
          f"{len(dataset.df)} bars | {len(X)} usable samples | ppy={ppy} | {dataset.note}\n")

    results = {}
    for name, factory in model_factories().items():
        try:
            wf = walk_forward(X, y, ret_next, factory, n_splits=args.splits)
            ev = evaluate_model(wf, ppy, args.threshold, args.cost_bps, args.long_only)
            results[name] = ev
            print(verdict_text(name, ev))
        except Exception as exc:
            print(f"  [{name}] skipped: {exc}")

    # Buy & hold context + leverage for the best *advanced* model with an edge.
    edged = [n for n in results if n in ADVANCED and results[n]["has_edge"]]
    print("\n--- Buy & hold benchmark ---")
    if results:
        bh = next(iter(results.values()))["buy_and_hold"]
        print(f"  Sharpe {bh['sharpe']:.2f} | ann_return {bh['ann_return']:.1%} | maxDD {bh['max_drawdown']:.1%}")

    if edged:
        best = max(edged, key=lambda n: results[n]["metrics"]["sharpe"])
        print(f"\n--- Leverage analysis [{best}] (only because an edge was proven) ---")
        for row in results[best]["leverage"]:
            warn = "  ⚠️ RUIN POSSIBLE" if row["ruin"] else ""
            print(f"  {row['leverage']:.0f}x: ann {row['ann_return']:.1%} | "
                  f"Sharpe {row['sharpe']:.2f} (≈ invariant) | maxDD {row['max_drawdown']:.1%}{warn}")
        print("  Note: leverage leaves Sharpe ~unchanged but scales drawdown — "
              "and under compounding amplifies it superlinearly (volatility drag).")
    else:
        print("\nNo advanced model proved an edge -> leverage NOT simulated "
              "(leveraging a non-edge only magnifies losses).")

    os.makedirs(args.out, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = os.path.join(args.out, f"{dataset.name.replace(':', '_')}_{stamp}.json")
    with open(path, "w") as f:
        json.dump({"dataset": dataset.name, "is_real": dataset.is_real,
                   "n_bars": len(dataset.df), "results": results}, f, indent=2)
    print(f"\nReport saved: {path}\n")


if __name__ == "__main__":
    main()
