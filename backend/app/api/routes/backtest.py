"""Backtesting route — run the engine over synthetic (or supplied) history."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_user_config
from app.backtest.engine import run_backtest
from app.models.config import TradingConfig
from app.models.user import User
from app.schemas.signal import BacktestRequest
from app.services.config_defaults import TradingConfigModel
from app.services.market_data import synthetic_ohlcv

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


@router.post("")
async def backtest(
    body: BacktestRequest,
    user: User = Depends(get_current_user),
    cfg: TradingConfig = Depends(get_user_config),
):
    # Use the user's saved config so enabled/disabled edges affect the backtest.
    config = TradingConfigModel(**(cfg.data or {}))
    sym_seed = (body.seed or 0) + sum(ord(c) for c in body.symbol)
    ohlcv = synthetic_ohlcv(bars=body.bars, seed=sym_seed)
    result = run_backtest(body.symbol, ohlcv, config, body.starting_equity)
    out = asdict(result)
    # Trim the equity curve for transport; keep a sampled view.
    if len(out["equity_curve"]) > 300:
        step = len(out["equity_curve"]) // 300
        out["equity_curve"] = out["equity_curve"][::step]
    return out
