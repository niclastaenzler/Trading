"""Async SQLAlchemy engine/session setup."""

from collections.abc import AsyncGenerator

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Portable JSON column: JSONB on PostgreSQL (production/Supabase), plain JSON
# elsewhere (e.g. SQLite in tests). Lets the ORM models run on either backend.
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


# `statement_cache_size=0` keeps asyncpg compatible with transaction-mode
# poolers (e.g. Supabase/PgBouncer on port 6543).
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    connect_args=(
        {"statement_cache_size": 0} if "pooler" in settings.database_url else {}
    ),
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a scoped async session."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_models() -> None:
    """Create tables for dev/first-run. Production should use Alembic."""
    # Import models so they register on Base.metadata.
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
