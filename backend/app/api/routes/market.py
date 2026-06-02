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
from app.services.market_data import fetch_ohlcv

router = APIRouter(prefix="/api/market", tags=["market"])


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
    Returns rows shaped for TradingView Lightweight-Charts (time in epoch secs)."""
    broker = _user_broker(user)
    try:
        await broker.connect()
    except Exception:
        pass
    try:
        df = await fetch_ohlcv(symbol, bars=min(bars, 500), broker=broker, timeframe=timeframe)
    except Exception:
        df = await fetch_ohlcv(symbol, bars=min(bars, 500))
    finally:
        if hasattr(broker, "aclose"):
            await broker.aclose()

    out = []
    idx = df.index
    for i, (_, row) in enumerate(df.iterrows()):
        ts = idx[i]
        t = int(pd.Timestamp(ts).timestamp()) if not isinstance(ts, (int, float)) else int(ts)
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
    return {"symbol": symbol, "timeframe": timeframe, "candles": clean}
