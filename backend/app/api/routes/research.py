"""Research routes — honest edge evaluation surfaced in the platform."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends

from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis import indicators
from app.api.deps import get_current_user, get_user_config, require_owner
from app.core.database import get_db
from app.core.encryption import decrypt
from app.models.config import TradingConfig
from app.models.user import User
from app.services.ai_engine import ai_model
from app.services.audit import log_audit
from app.services.broker import get_broker
from app.services.config_defaults import TradingConfigModel
from app.services.market_data import fetch_ohlcv
from app.services.model_store import latest_model_row, save_model
from app.services.universe import all_symbols

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


@router.get("/model")
async def model_status(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Status of the trained model: whether one is loaded, when, scores, features."""
    row = await latest_model_row(db)
    return {
        "is_trained": ai_model.is_trained,
        "trained_at": str(row.trained_at) if row else None,
        "metrics": row.metrics if row else {},
        "feature_importance": (row.features if row else []) or ai_model.feature_importance(),
    }


@router.post("/train")
async def train_model(
    bars: int = 1000,
    max_symbols: int = 12,
    cfg: TradingConfig = Depends(get_user_config),
    user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """Train ONE pooled multi-asset model on the configured universe's history
    (a basic cross-sectional model), persist it, and load it live."""
    return await train_user_model(db, user, cfg.data, bars=bars, max_symbols=max_symbols)


async def train_user_model(
    db: AsyncSession,
    user: User,
    cfg_data: dict | None,
    *,
    bars: int = 1000,
    max_symbols: int = 12,
) -> dict:
    """Reusable training core (shared by the /train route and the autopilot cron).
    Fetches the configured universe's history, trains the pooled model, persists
    and loads it. Returns a result dict with `ok`."""
    model = TradingConfigModel(**(cfg_data or {}))
    params = model.strategy.indicators
    symbols = (cfg_data or {}).get("trading", {}).get("allowed_symbols") or all_symbols()
    symbols = symbols[:max_symbols]

    creds = {}
    if user.broker_credentials_enc:
        try:
            creds = json.loads(decrypt(user.broker_credentials_enc))
        except ValueError:
            creds = {}
    broker = get_broker(user.id, user.broker_name, creds)
    try:
        await broker.connect()
    except Exception:
        pass

    frames = []
    used = []
    try:
        for sym in symbols:
            try:
                df = await fetch_ohlcv(sym, bars=min(bars, 1500), broker=broker, timeframe="1d")
                enriched = indicators.compute_all(df, params)
                frames.append(enriched)
                used.append(sym)
            except Exception:
                continue
    finally:
        if hasattr(broker, "aclose"):
            await broker.aclose()

    try:
        result = ai_model.train_pooled(frames)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}

    await save_model(db, user.id, result.get("feature_importance", []), {
        k: result[k] for k in ("instruments", "trained_on", "tested_on", "train_score", "test_score")
    })
    await log_audit(db, event="MODEL_TRAINED", user_id=user.id,
                    message=f"trained pooled model on {len(used)} instruments",
                    context={"symbols": used, "test_score": result.get("test_score")})
    result["ok"] = True
    result["symbols"] = used
    return result
