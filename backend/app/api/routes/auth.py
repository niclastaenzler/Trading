"""Auth routes: register (first user becomes owner), login."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.config import TradingConfig
from app.models.user import User
from app.schemas.auth import RegisterRequest, TokenResponse, UserOut
from app.services.audit import log_audit
from app.services.config_defaults import default_config

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Protect a public instance: if an invite code is configured, require it.
    if settings.registration_invite_code:
        if (body.invite_code or "") != settings.registration_invite_code:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid or missing invite code")

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    count = await db.scalar(select(func.count(User.id)))
    # First account is the owner; subsequent are viewers (single-user focus).
    role = "owner" if (count or 0) == 0 else "viewer"

    user = User(email=body.email, hashed_password=hash_password(body.password), role=role)
    db.add(user)
    await db.flush()
    db.add(
        TradingConfig(user_id=user.id, data=default_config().model_dump(mode="json"))
    )
    await log_audit(db, event="USER_REGISTERED", user_id=user.id,
                    message=f"registered {body.email} as {role}")
    await db.flush()
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    token = create_access_token(str(user.id), {"role": user.role})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
