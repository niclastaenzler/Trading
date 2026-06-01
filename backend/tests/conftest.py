"""Pytest fixtures.

Unit tests need only the import path. Integration tests get an isolated app
instance backed by in-memory SQLite + fakeredis, with the DB dependency
overridden and Redis patched — no Postgres/Redis required to run the suite.
"""

import os
import sys
from pathlib import Path

import pytest_asyncio

# Make `app` importable when running pytest from the backend/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("ENABLE_SCHEDULER", "0")
os.environ.setdefault("SKIP_DB_INIT", "1")


@pytest_asyncio.fixture
async def client():
    import fakeredis.aioredis
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    import app.models  # noqa: F401 — register tables
    from app.core import redis_client
    from app.core.database import Base, get_db
    from app.main import app

    # Shared in-memory DB (StaticPool keeps a single connection alive).
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    TestSession = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with TestSession() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # Patch the Redis singleton with an in-process fake.
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    redis_client._redis = fake

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Expose the sessionmaker so tests can seed rows directly.
        ac.test_sessionmaker = TestSession
        yield ac

    app.dependency_overrides.clear()
    redis_client._redis = None
    await fake.aclose()
    await engine.dispose()


@pytest_asyncio.fixture
async def owner_client(client):
    """An authenticated owner client (first registered account = owner)."""
    await client.post(
        "/api/auth/register", json={"email": "owner@test.io", "password": "pw123456"}
    )
    res = await client.post(
        "/api/auth/login",
        data={"username": "owner@test.io", "password": "pw123456"},
    )
    token = res.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client
