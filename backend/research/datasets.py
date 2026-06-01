"""Data loaders for the research harness.

Real-data loaders fetch history **up to the present** (train on the past,
predict the latest bar). In this sandbox the network allowlist blocks live
market hosts, so `load_binance` / `load_yfinance` will fail here but work in any
normal environment or the deployed app; the broker loader reuses the app's
Capital.com integration. Synthetic generators provide *known-ground-truth*
controls to validate that the edge detector behaves correctly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Dataset:
    name: str
    df: pd.DataFrame              # OHLCV, DatetimeIndex
    periods_per_year: int         # 252 equities, 365 daily crypto, etc.
    is_real: bool
    note: str = ""


# ───────────────────────── real, current data ─────────────────────────
def load_binance(symbol: str = "BTCUSDT", interval: str = "1d", limit: int = 1000) -> Dataset:
    """Current OHLCV from Binance's public REST API (no auth, ends at now)."""
    import httpx

    url = "https://api.binance.com/api/v3/klines"
    resp = httpx.get(url, params={"symbol": symbol, "interval": interval, "limit": limit}, timeout=20)
    resp.raise_for_status()
    rows = resp.json()
    df = pd.DataFrame(
        rows,
        columns=["open_time", "open", "high", "low", "close", "volume",
                 "close_time", "qav", "trades", "tbav", "tbqv", "ignore"],
    )
    df.index = pd.to_datetime(df["open_time"], unit="ms")
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    ppy = 365 if interval.endswith("d") else 365 * 24
    return Dataset(f"binance:{symbol}:{interval}", df, ppy, True, "live Binance data")


def load_yfinance(symbol: str = "SPY", period: str = "10y", interval: str = "1d") -> Dataset:
    """Current OHLCV via yfinance (optional dependency)."""
    import yfinance as yf

    df = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False)
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna()
    return Dataset(f"yfinance:{symbol}", df, 252, True, "live yfinance data")


async def load_broker(symbol: str, broker, resolution: str = "DAY", limit: int = 1000) -> Dataset:
    """Current candles via the app's broker integration (e.g. Capital.com)."""
    candles = await broker.get_candles(symbol, resolution=resolution, limit=limit)
    if candles is None or len(candles) < 100:
        raise RuntimeError(f"broker returned insufficient candles for {symbol}")
    ppy = 365 if resolution.upper().startswith("DAY") else 252
    return Dataset(f"broker:{symbol}", candles, ppy, True, f"live broker {broker.name}")


def load_csv(path: str, periods_per_year: int = 252) -> Dataset:
    """Load OHLCV from a CSV with auto-detected column names + a date column."""
    raw = pd.read_csv(path)
    cols = {c.lower(): c for c in raw.columns}

    def pick(*names):
        for n in names:
            for low, orig in cols.items():
                if low.endswith(n) or low == n:
                    return orig
        raise KeyError(f"no column matching {names}")

    date_col = pick("date", "time", "timestamp", "datetime")
    out = pd.DataFrame(
        {
            "open": raw[pick("open")].astype(float),
            "high": raw[pick("high")].astype(float),
            "low": raw[pick("low")].astype(float),
            "close": raw[pick("close")].astype(float),
        }
    )
    try:
        out["volume"] = raw[pick("volume")].astype(float)
    except KeyError:
        out["volume"] = 0.0
    out.index = pd.to_datetime(raw[date_col])
    out = out.sort_index()
    return Dataset(f"csv:{path.split('/')[-1]}", out, periods_per_year, True, "CSV file")


# ───────────────────────── controlled synthetic data ─────────────────────────
def _ohlc_from_close(close: np.ndarray, rng: np.random.Generator) -> pd.DataFrame:
    n = len(close)
    open_ = np.concatenate([[close[0]], close[:-1]])
    noise = np.abs(rng.normal(0, 0.003, n)) * close
    high = np.maximum(open_, close) + noise
    low = np.minimum(open_, close) - noise
    idx = pd.date_range(end=pd.Timestamp.now(tz="UTC").normalize(), periods=n, freq="D")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close,
         "volume": rng.integers(1e6, 5e6, n).astype(float)},
        index=idx,
    )


def make_random_walk(n: int = 1500, seed: int = 0, drift: float = 0.0002, vol: float = 0.01) -> Dataset:
    """Efficient market (no edge by construction). Detector MUST report NO edge."""
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, n)
    close = 100 * np.exp(np.cumsum(rets))
    return Dataset("synthetic:random_walk", _ohlc_from_close(close, rng), 365, False,
                   "GBM control — no predictability")


def make_predictable(n: int = 1500, seed: int = 0, phi: float = 0.25, vol: float = 0.01) -> Dataset:
    """AR(1) returns: r_t = phi*r_{t-1} + eps. Positive phi => past return predicts
    next direction. Controlled edge of tunable strength. Detector MUST find it."""
    rng = np.random.default_rng(seed)
    eps = rng.normal(0, vol, n)
    r = np.zeros(n)
    for t in range(1, n):
        r[t] = phi * r[t - 1] + eps[t]
    close = 100 * np.exp(np.cumsum(r))
    return Dataset(f"synthetic:predictable(phi={phi})", _ohlc_from_close(close, rng), 365,
                   False, "AR(1) control — known momentum edge")
