# Edge Research Harness

A methodically honest pipeline to **search for** and **evaluate** a statistical
trading edge. The default stance is *"no edge"* until the data proves otherwise
across several independent tests. No hype, no curve-fitting to noise.

## Pipeline

1. **Feature engineering** (`features.py`) — returns/log-returns, rolling
   volatility, momentum, RSI, moving-average relationships, MACD, ATR, volume
   spike z-score, and optional **news/sentiment** features. Every feature is
   **strictly backward-looking**; a unit test asserts feature values at bar *t*
   do not change when future bars are appended (no lookahead bias).
2. **Models** (`models.py`) — under one interface:
   - baselines: `random`, `majority-class`, `persistence` (naive momentum)
   - `logistic` regression (scaler fit per-fold only)
   - `gradient boosting` (XGBoost if installed, else sklearn)
3. **Validation** (`walkforward.py`) — expanding-window **walk-forward**, never a
   random split, with an **embargo** equal to the longest feature window so
   train/test never share a rolling computation.
4. **Edge analysis** (`edge_analysis.py`) — realistic simulation with
   transaction costs; hit-rate, Sharpe, max drawdown; **three** significance
   tests (binomial on hit-rate, t-test on returns, and a **Monte-Carlo vs
   random** positions test); fold consistency; buy & hold benchmark.
5. **Leverage** (`edge_analysis.leverage_analysis`) — simulated **only if an edge
   is proven**. Shows that Sharpe is ~leverage-invariant while drawdown grows
   (superlinearly under compounding — volatility drag).
6. **Verdict** (`report.py`) — edge credited only if it clears *every* hurdle.

## Run it

```bash
cd backend
# (optional) fetch the small real demo dataset referenced below:
mkdir -p research/data && curl -sL -o research/data/aapl.csv \
  https://raw.githubusercontent.com/plotly/datasets/master/finance-charts-apple.csv

# Validate the detector on known-truth controls:
python -m research.run_research --dataset random        # MUST report NO edge
python -m research.run_research --dataset predictable    # MUST report EDGE

# Real data:
python -m research.run_research --dataset csv --csv research/data/aapl.csv --ppy 252
python -m research.run_research --dataset binance --symbol BTCUSDT --interval 1d   # current crypto (needs network)
python -m research.run_research --dataset yfinance --symbol SPY                    # needs yfinance + network

# Current candles via your broker demo account (e.g. Capital.com):
export BROKER=capital_com CAPITAL_COM_API_KEY=... CAPITAL_COM_IDENTIFIER=... \
       CAPITAL_COM_PASSWORD=... CAPITAL_COM_DEMO=true
python -m research.run_research --dataset broker --symbol EURUSD --resolution DAY --limit 1000
# resolution: MINUTE / MINUTE_5 / MINUTE_15 / HOUR / HOUR_4 / DAY
# symbol = the broker's "epic" (e.g. EURUSD, US500, BTCUSD on Capital.com)
```

## ⚠️ Current data & this sandbox

This research environment's **network allowlist blocks all live market-data
hosts** (Yahoo, stooq, Binance, Coinbase, Kraken, Capital.com, …); only PyPI and
GitHub are reachable. So **current** prices cannot be fetched *here*.

- `load_binance` / `load_yfinance` / `load_broker` fetch history **up to the
  present** and work in any normal environment or the deployed app (where the
  broker/exchange hosts are reachable). Train on the past, predict the latest bar.
- In this sandbox the harness is validated on **controlled synthetic data**
  (known ground truth) plus a small **historical** AAPL CSV (2015–2017), which is
  enough to prove the methodology is sound — not to make a live trading claim.

To run on **current** data: execute the commands above in an environment with
network access (or wire `load_broker` to your Capital.com candles), or extend the
allowlist to your data provider.

## Honest findings so far

| Dataset | Type | Verdict |
|---|---|---|
| `random_walk` | control (no signal) | ❌ no edge — *correct* |
| `predictable` (AR1) | control (known signal) | ✅ edge found, leverage-invariant Sharpe — *correct* |
| AAPL daily 2015–2017 | real, historical, ~456 samples | ❌ **no robust edge** — buy & hold (Sharpe 2.61) beats every model; daily direction is ~unpredictable on this sample |

**Is there a real edge? On the data testable here: No.** Daily next-bar
direction on a single liquid stock is essentially efficient — models score ≈50%
out-of-sample, and none beat random or buy & hold. This is the expected,
honest result; a small single-asset daily sample rarely contains a robust,
cost-surviving edge.

### Concrete next steps to actually find an edge
- **More & current data**: years of history across many assets (cross-sectional
  models generalise far better than one ticker); intraday bars for more samples.
- **Better targets**: volatility-scaled returns, multi-bar horizons, or
  cross-sectional rank (relative strength) instead of raw single-asset direction.
- **Real exogenous features**: order-flow/microstructure, funding rates (crypto),
  genuine news/sentiment feeds (the hook exists in `add_news_features`).
- **Regime conditioning**: edges are often regime-specific (trend vs chop);
  evaluate per-regime rather than pooling.
- Keep the **same strict validation** — walk-forward, costs, MC-vs-random — so
  any edge found is real and not a backtest artefact.
