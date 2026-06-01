"""Shared API dependencies: auth + config loading."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.config import TradingConfig
from app.models.user import User
from app.services.config_defaults import default_config

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    result = await db.execute(select(User).where(User.id == int(payload["sub"])))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found/inactive")
    return user


async def require_owner(user: User = Depends(get_current_user)) -> User:
    """Mutating actions (trading, config) require the owner role."""
    if user.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Owner role required")
    return user


async def get_user_config(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TradingConfig:
    result = await db.execute(
        select(TradingConfig).where(TradingConfig.user_id == user.id)
    )
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = TradingConfig(user_id=user.id, data=default_config().model_dump(mode="json"))
        db.add(cfg)
        await db.flush()
    return cfg
