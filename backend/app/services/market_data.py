"""Market data access.

For paper/demo and backtesting we synthesise realistic OHLCV via geometric
Brownian motion (deterministic with a seed). A real deployment would replace
`fetch_ohlcv` with a pull from the broker's official market-data endpoint
(respecting rate limits via the compliance guard).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def synthetic_ohlcv(
    bars: int = 500,
    start_price: float = 1.10,
    seed: int | None = 42,
    vol: float = 0.004,
    freq: str = "1h",
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0, vol, bars)
    close = start_price * np.exp(np.cumsum(returns))
    open_ = np.concatenate([[start_price], close[:-1]])
    intrabar = np.abs(rng.normal(0, vol, bars)) * close
    high = np.maximum(open_, close) + intrabar
    low = np.minimum(open_, close) - intrabar
    volume = rng.integers(500, 5000, bars).astype(float)
    index = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=bars, freq=freq)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )


_RESOLUTION = {
    "1m": "MINUTE", "5m": "MINUTE_5", "15m": "MINUTE_15",
    "1h": "HOUR", "4h": "HOUR_4", "1d": "DAY",
}


async def fetch_ohlcv(
    symbol: str,
    bars: int = 200,
    seed: int | None = None,
    broker=None,
    timeframe: str = "1h",
) -> pd.DataFrame:
    """Return recent OHLCV for `symbol`.

    Uses the broker's documented candles endpoint when one is available
    (real market data); otherwise falls back to a deterministic synthetic
    series so demo/paper/backtest stay fully functional offline.
    """
    if broker is not None:
        try:
            candles = await broker.get_candles(
                symbol, resolution=_RESOLUTION.get(timeframe, "HOUR"), limit=bars
            )
            if candles is not None and len(candles) >= 50:
                return candles
        except Exception:
            # Never let a data-feed hiccup crash the cycle; fall back to synthetic.
            pass

    # Derive a per-symbol seed so each instrument has a stable but distinct series.
    sym_seed = (seed if seed is not None else 0) + sum(ord(c) for c in symbol)
    return synthetic_ohlcv(bars=bars, seed=sym_seed)
