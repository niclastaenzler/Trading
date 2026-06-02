"""Research routes — honest edge evaluation surfaced in the platform."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.encryption import decrypt
from app.models.user import User
from app.services.broker import get_broker
from app.services.market_data import fetch_ohlcv

router = APIRouter(prefix="/api/research", tags=["research"])


def _user_broker(user: User):
    creds = {}
    if user.broker_credentials_enc:
        try:
            creds = json.loads(decrypt(user.broker_credentials_enc))
        except ValueError:
            creds = {}
    return get_broker(user.id, user.broker_name, creds)


@router.get("/edge")
async def edge(
    symbol: str = "EURUSD",
    timeframe: str = "1d",
    bars: int = 1000,
    user: User = Depends(get_current_user),
):
    """Walk-forward edge evaluation for `symbol` — honest YES/NO + next steps.

    Uses the broker's candle history when available (real data), else synthetic.
    Heavy-ish; intended for an on-demand button, not every refresh.
    """
    from research.service import evaluate_symbol  # local import keeps startup light

    broker = _user_broker(user)
    try:
        await broker.connect()
    except Exception:
        pass
    try:
        df = await fetch_ohlcv(symbol, bars=min(bars, 1500), broker=broker, timeframe=timeframe)
    finally:
        if hasattr(broker, "aclose"):
            await broker.aclose()

    ppy = 365 if timeframe.endswith("d") else 252
    result = evaluate_symbol(df, ppy=ppy)
    result["symbol"] = symbol
    result["timeframe"] = timeframe
    return result
