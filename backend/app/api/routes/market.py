"""Market data routes — OHLCV candles for the live trading chart."""

from __future__ import annotations

import json
import math

import pandas as pd
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.encryption import decrypt
from app.models.user import User
from app.services.broker import get_broker
from app.services.market_data import _RESOLUTION, fetch_ohlcv
from app.services.universe import UNIVERSE, all_symbols

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/universe")
async def market_universe(user: User = Depends(get_current_user)):
    """Tradable universe grouped by asset class (forex, commodities, indices,
    stocks) — used by the config UI to build a multi-asset portfolio."""
    return {"groups": UNIVERSE, "all": all_symbols()}


def _user_broker(user: User):
    creds = {}
    if user.broker_credentials_enc:
        try:
            creds = json.loads(decrypt(user.broker_credentials_enc))
        except ValueError:
            creds = {}
    return get_broker(user.id, user.broker_name, creds)


@router.get("/candles")
async def candles(
    symbol: str = "EURUSD",
    timeframe: str = "1h",
    bars: int = 200,
    user: User = Depends(get_current_user),
):
    """OHLCV candles for `symbol`. Uses the user's broker feed when available
    (e.g. Capital.com), otherwise a synthetic series so the chart always renders.
    Returns the data SOURCE so the dashboard can show whether it is live broker
    data or the synthetic fallback. Times are epoch seconds (UTC)."""
    broker = _user_broker(user)
    df = None
    source = "synthetic"
    try:
        await broker.connect()
        live = await broker.get_candles(
            symbol, resolution=_RESOLUTION.get(timeframe, "HOUR"), limit=min(bars, 500)
        )
        if live is not None and len(live) >= 30:
            df, source = live, broker.name
    except Exception:
        df = None
    finally:
        if hasattr(broker, "aclose"):
            await broker.aclose()

    if df is None:
        df = await fetch_ohlcv(symbol, bars=min(bars, 500))  # synthetic fallback
        source = "synthetic"

    out = []
    idx = df.index
    for i in range(len(df)):
        row = df.iloc[i]
        ts = idx[i]
        if isinstance(ts, (int, float)):
            t = int(ts)
        else:
            ts = pd.Timestamp(ts)
            if ts.tzinfo is None:  # broker times are UTC — localize so epoch is correct
                ts = ts.tz_localize("UTC")
            t = int(ts.timestamp())
        o, h, l, c = (float(row["open"]), float(row["high"]),
                      float(row["low"]), float(row["close"]))
        if any(math.isnan(v) for v in (o, h, l, c)):
            continue
        out.append({"time": t, "open": o, "high": h, "low": l, "close": c})

    # Lightweight-charts requires strictly ascending, unique timestamps.
    seen, clean = set(), []
    for r in out:
        if r["time"] in seen:
            r["time"] = (clean[-1]["time"] + 1) if clean else r["time"]
        seen.add(r["time"])
        clean.append(r)
    return {
        "symbol": symbol, "timeframe": timeframe,
        "source": source, "live": source != "synthetic", "candles": clean,
    }
