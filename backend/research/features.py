"""No-lookahead feature engineering.

Every feature at bar t is computed from information available **at or before the
close of t**. The prediction target is the *next* bar's return, so there is a
strict 1-bar gap between features and outcome. Critically:

  * No feature uses future rows (all rolling/ewm ops are backward-looking).
  * No global scaling here — any normalisation that needs statistics is fit on
    the training fold only, inside the walk-forward (see models/walkforward).

`MAX_WINDOW` is the longest lookback; the walk-forward uses it as the embargo so
train and test folds never share a rolling window.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.analysis import indicators

MAX_WINDOW = 50

# Feature columns produced by `build_features` (price-only set).
PRICE_FEATURES = [
    "ret_1", "log_ret_1", "ret_2", "ret_5", "ret_10",
    "vol_5", "vol_10", "vol_20",
    "mom_10", "mom_20", "rsi_14",
    "sma_ratio_10", "sma_ratio_20", "sma_ratio_50",
    "ema_ratio_fast", "sma_cross", "macd_hist_n", "atr_ratio", "vol_z",
]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame of backward-looking features aligned to `df.index`."""
    close, vol = df["close"], df.get("volume", pd.Series(0.0, index=df.index))
    log_ret = np.log(close).diff()
    feat = pd.DataFrame(index=df.index)

    # Returns / log-returns.
    feat["ret_1"] = close.pct_change(1)
    feat["log_ret_1"] = log_ret
    feat["ret_2"] = close.pct_change(2)
    feat["ret_5"] = close.pct_change(5)
    feat["ret_10"] = close.pct_change(10)

    # Rolling realised volatility (of log-returns).
    feat["vol_5"] = log_ret.rolling(5).std()
    feat["vol_10"] = log_ret.rolling(10).std()
    feat["vol_20"] = log_ret.rolling(20).std()

    # Momentum.
    feat["mom_10"] = close / close.shift(10) - 1
    feat["mom_20"] = close / close.shift(20) - 1
    feat["rsi_14"] = indicators.rsi(close, 14)

    # Moving-average relationships.
    feat["sma_ratio_10"] = close / close.rolling(10).mean() - 1
    feat["sma_ratio_20"] = close / close.rolling(20).mean() - 1
    feat["sma_ratio_50"] = close / close.rolling(50).mean() - 1
    feat["ema_ratio_fast"] = close / indicators.ema(close, 12) - 1
    feat["sma_cross"] = (
        close.rolling(10).mean() / close.rolling(50).mean() - 1
    )

    # MACD histogram, normalised by price; ATR ratio.
    macd_df = indicators.macd(close, 12, 26, 9)
    feat["macd_hist_n"] = macd_df["hist"] / close
    feat["atr_ratio"] = indicators.atr(df, 14) / close

    # Volume spike z-score (past-only rolling stats).
    vmean = vol.rolling(20).mean()
    vstd = vol.rolling(20).std()
    feat["vol_z"] = ((vol - vmean) / vstd.replace(0, np.nan)).fillna(0.0)

    return feat[PRICE_FEATURES]


def add_news_features(
    feat: pd.DataFrame,
    news: pd.DataFrame,
    lag_bars: int = 1,
) -> pd.DataFrame:
    """Attach optional news/sentiment features (past-only).

    `news` must have a DatetimeIndex and columns:
        sentiment : float in [-1, 1] per article/window
        count     : number of articles in that window
    Features are resampled to the price index, then **shifted by `lag_bars`** so
    only news strictly before the decision bar is used (no same-bar leak).
    """
    if news is None or news.empty:
        return feat
    daily = news.resample("D").agg(sentiment=("sentiment", "mean"),
                                   count=("count", "sum"))
    aligned = daily.reindex(feat.index.normalize().unique()).ffill()
    aligned.index = feat.index.normalize().unique()

    s = aligned["sentiment"].reindex(feat.index, method="ffill")
    c = aligned["count"].reindex(feat.index, method="ffill").fillna(0.0)

    out = feat.copy()
    out["news_sentiment"] = s.rolling(3).mean().shift(lag_bars)
    cmean, cstd = c.rolling(20).mean(), c.rolling(20).std()
    out["news_spike_z"] = ((c - cmean) / cstd.replace(0, np.nan)).shift(lag_bars)
    return out.fillna(0.0)


def build_dataset(df: pd.DataFrame, news: pd.DataFrame | None = None):
    """Assemble (X, y, ret_next) with the warmup and final (no-future) row dropped.

    Target: direction of the NEXT bar's return.
      ret_next[t] = close[t+1]/close[t] - 1
      y[t]        = 1 if ret_next[t] > 0 else 0
    """
    feat = build_features(df)
    if news is not None:
        feat = add_news_features(feat, news)

    ret_next = df["close"].pct_change().shift(-1)
    y = (ret_next > 0).astype(int)

    data = feat.copy()
    data["__ret_next"] = ret_next
    data["__y"] = y
    data = data.dropna()  # drops warmup rows and the last (no future) row

    feature_cols = [c for c in data.columns if not c.startswith("__")]
    return data[feature_cols], data["__y"], data["__ret_next"]
