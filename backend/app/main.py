"""FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    auth,
    backtest,
    config,
    market,
    research,
    trades,
    trading,
    webhooks,
    ws,
)
from app.config import settings
from app.core.database import init_models
from app.core.logging_config import configure_logging, get_logger
from app.core.redis_client import get_redis
from app.services.scheduler import scheduler_loop

logger = get_logger("main")


def _production_safety_checks() -> None:
    """Refuse to start in production with insecure defaults."""
    if not settings.is_production:
        return
    problems = []
    if settings.jwt_secret_key in ("", "dev-insecure-change-me"):
        problems.append("JWT_SECRET_KEY is not set")
    if not settings.encryption_key:
        problems.append("ENCRYPTION_KEY is not set (cannot encrypt credentials)")
    if settings.broker != "paper" and settings.capital_com_demo is False:
        logger.warning("LIVE trading broker configured in production")
    if problems:
        raise RuntimeError("Unsafe production config: " + "; ".join(problems))


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("INFO" if settings.is_production else "DEBUG")
    _production_safety_checks()
    logger.info("starting %s", settings.app_name, extra={"env": settings.app_env})

    if os.getenv("SKIP_DB_INIT") != "1":
        await init_models()
        # Load the most recently trained model so it survives restarts.
        try:
            from app.core.database import SessionLocal
            from app.services.model_store import load_latest_model

            async with SessionLocal() as db:
                await load_latest_model(db)
        except Exception as exc:  # pragma: no cover
            logger.warning("could not load trained model: %s", exc)
    try:
        await get_redis().ping()
    except Exception as exc:  # pragma: no cover
        logger.warning("redis not reachable at startup: %s", exc)

    stop_event = asyncio.Event()
    scheduler_task = None
    if os.getenv("ENABLE_SCHEDULER", "1") == "1":
        scheduler_task = asyncio.create_task(scheduler_loop(stop_event))

    try:
        yield
    finally:
        stop_event.set()
        if scheduler_task:
            await scheduler_task


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Compliant, single-user AI trading platform (MVP).",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (auth, config, trading, trades, backtest, market, research, webhooks):
    app.include_router(module.router)
app.include_router(ws.router)


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok", "env": settings.app_env, "broker_default": settings.broker}


@app.get("/", tags=["meta"])
async def root():
    return {"name": settings.app_name, "docs": "/docs"}
