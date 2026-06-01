"""Configuration routes — read/update the full trading config and runtime flags.

All writes go through `TradingConfigModel`, so reckless values are clamped or
rejected before they ever reach the engine.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_user_config, require_owner
from app.core.database import get_db
from app.models.config import TradingConfig
from app.models.user import User
from app.schemas.signal import AutomationToggle, ConfigOut, ConfigUpdate
from app.services.audit import log_audit
from app.services.config_defaults import TradingConfigModel, default_config

router = APIRouter(prefix="/api/config", tags=["config"])


def _to_out(cfg: TradingConfig) -> ConfigOut:
    return ConfigOut(
        config=cfg.data,
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
