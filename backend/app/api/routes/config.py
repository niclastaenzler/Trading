"""Configuration routes — read/update the full trading config and runtime flags.

All writes go through `TradingConfigModel`, so reckless values are clamped or
rejected before they ever reach the engine.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_user_config, require_owner
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.models.config import TradingConfig
from app.models.trade import Order, Trade
from app.models.user import User
from app.schemas.signal import AutomationToggle, ConfigOut, ConfigUpdate
from app.services.audit import log_audit
from app.services.config_defaults import TradingConfigModel, default_config

router = APIRouter(prefix="/api/config", tags=["config"])


def _to_out(cfg: TradingConfig) -> ConfigOut:
    # Return the validated/normalised config so newly added fields (edge layer,
    # confidence sizing, …) always appear with sane defaults for the UI, even if
    # the stored JSON predates them.
    normalised = TradingConfigModel(**(cfg.data or {})).model_dump(mode="json")
    return ConfigOut(
        config=normalised,
        auto_trading_enabled=cfg.auto_trading_enabled,
        kill_switch_active=cfg.kill_switch_active,
        version=cfg.version,
    )


@router.get("", response_model=ConfigOut)
async def get_config(cfg: TradingConfig = Depends(get_user_config)):
    return _to_out(cfg)


@router.get("/defaults", response_model=dict)
async def get_defaults():
    """Expose the safe defaults (useful for the frontend's reset button)."""
    return default_config().model_dump(mode="json")


@router.put("", response_model=ConfigOut)
async def update_config(
    body: ConfigUpdate,
    cfg: TradingConfig = Depends(get_user_config),
    user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    # Re-validate through the model so the compliance envelope is re-applied.
    validated = TradingConfigModel(**body.config.model_dump())
    cfg.data = validated.model_dump(mode="json")
    cfg.version += 1
    await log_audit(db, event="CONFIG_UPDATE", user_id=user.id,
                    message=f"config updated -> v{cfg.version}")
    return _to_out(cfg)


@router.post("/automation", response_model=ConfigOut)
async def toggle_automation(
    body: AutomationToggle,
    cfg: TradingConfig = Depends(get_user_config),
    user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    # The kill switch always wins: cannot enable auto-trading while it is active.
    if body.auto_trading_enabled and cfg.kill_switch_active:
        cfg.auto_trading_enabled = False
        await log_audit(db, event="AUTOMATION_BLOCKED", user_id=user.id,
                        message="auto-trading blocked: kill switch active",
                        severity="warning")
    else:
        cfg.auto_trading_enabled = body.auto_trading_enabled
        await log_audit(db, event="AUTOMATION_TOGGLE", user_id=user.id,
                        message=f"auto-trading -> {cfg.auto_trading_enabled}")
    return _to_out(cfg)


@router.post("/kill-switch", response_model=ConfigOut)
async def kill_switch(
    activate: bool = True,
    cfg: TradingConfig = Depends(get_user_config),
    user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """Emergency stop: halts all automated trading immediately."""
    cfg.kill_switch_active = activate
    if activate:
        cfg.auto_trading_enabled = False
    await log_audit(db, event="KILL_SWITCH", user_id=user.id,
                    message=f"kill switch {'ACTIVATED' if activate else 'cleared'}",
                    severity="critical" if activate else "info")
    return _to_out(cfg)


@router.post("/reset-account", response_model=dict)
async def reset_account(
    cfg: TradingConfig = Depends(get_user_config),
    user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """Full clean slate for the (paper) account.

    Wipes the trade/order history that feeds the daily-loss and drawdown halts,
    resets the paper balance and open positions, clears the all-time peak equity
    and any pending confirmations, and lifts the kill switch. The user's config
    settings (risk, markets, …) are left untouched — this resets *state*, not
    preferences. Auto-trading is left off so nothing fires before the user opts
    back in.
    """
    # 1. Count then delete this user's trade & order history (resets realized PnL).
    n_trades = (
        await db.execute(select(func.count()).select_from(Trade).where(Trade.user_id == user.id))
    ).scalar_one()
    n_orders = (
        await db.execute(select(func.count()).select_from(Order).where(Order.user_id == user.id))
    ).scalar_one()
    await db.execute(delete(Trade).where(Trade.user_id == user.id))
    await db.execute(delete(Order).where(Order.user_id == user.id))

    # 2. Clear all Redis runtime state for this user.
    redis = get_redis()
    keys = [
        f"paper:{user.id}:balance",
        f"paper:{user.id}:positions",
        f"user:{user.id}:peak_equity",
        f"user:{user.id}:last_model_train",
    ]
    try:
        pending = await redis.keys(f"user:{user.id}:pending:*")
        keys.extend(k.decode() if isinstance(k, bytes) else k for k in (pending or []))
        if keys:
            await redis.delete(*keys)
    except Exception:  # pragma: no cover - reset must not fail on a cache hiccup
        pass

    # 3. Lift halts; leave auto-trading off so trading only resumes deliberately.
    cfg.kill_switch_active = False
    cfg.auto_trading_enabled = False

    await log_audit(db, event="ACCOUNT_RESET", user_id=user.id,
                    message=f"account reset: {n_trades} trades, {n_orders} orders cleared",
                    severity="warning")
    await db.commit()
    return {
        "ok": True,
        "trades_deleted": int(n_trades),
        "orders_deleted": int(n_orders),
        "message": "Konto zurückgesetzt: Verlauf gelöscht, Kontostand & Höchststand "
                   "zurückgesetzt, Tagesverlust = 0, Not-Aus aufgehoben.",
    }
