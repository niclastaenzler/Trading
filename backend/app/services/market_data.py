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


async def fetch_ohlcv(symbol: str, bars: int = 200, seed: int | None = None) -> pd.DataFrame:
    """Return recent OHLCV for `symbol`.

    Paper/demo path uses synthetic data. Swap this for the broker's documented
    candles endpoint in production.
    """
    # Derive a per-symbol seed so each instrument has a stable but distinct series.
    sym_seed = (seed if seed is not None else 0) + sum(ord(c) for c in symbol)
    return synthetic_ohlcv(bars=bars, seed=sym_seed)
