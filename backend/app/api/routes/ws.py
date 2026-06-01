"""WebSocket endpoint streaming real-time signals & events to the dashboard.

Subscribes to the Redis pub/sub channels and forwards messages to the client.
Auth is via a `token` query param (browsers can't set WS headers easily).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.logging_config import get_logger
from app.core.redis_client import EVENTS_CHANNEL, SIGNAL_CHANNEL, get_redis
from app.core.security import decode_access_token

router = APIRouter(tags=["ws"])
logger = get_logger("ws")


@router.websocket("/ws")
async def ws_stream(websocket: WebSocket, token: str = Query(...)):
    payload = decode_access_token(token)
    if not payload:
        await websocket.close(code=4401)
        return
    await websocket.accept()

    pubsub = get_redis().pubsub()
    await pubsub.subscribe(SIGNAL_CHANNEL, EVENTS_CHANNEL)
    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if message and message.get("type") == "message":
                await websocket.send_text(message["data"])
            else:
                # Heartbeat keeps proxies from dropping idle connections.
                await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(SIGNAL_CHANNEL, EVENTS_CHANNEL)
        await pubsub.close()
