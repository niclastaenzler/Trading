"""Capital.com broker adapter — official REST API only.

Docs: https://open-api.capital.com/  (documented, supported public API).
Auth flow: POST /session with X-CAP-API-KEY header + identifier/password,
returns CST and X-SECURITY-TOKEN headers used for subsequent calls.

Compliance notes:
  * Uses only documented endpoints (no scraping / no reverse engineering).
  * All requests go through the caller's RateLimiter (compliance guard).
  * Defaults to the DEMO environment; live requires explicit opt-in.

This adapter is network-bound; it is exercised in integration (not unit) tests.
"""

from __future__ import annotations

import hashlib
import json

import httpx
import pandas as pd

from app.core.logging_config import get_logger
from app.core.redis_client import get_redis
from app.services.broker.broker_interface import (
    BrokerInterface,
    BrokerOrder,
    BrokerPosition,
)

logger = get_logger("broker.capital_com")

# Capital.com sessions stay valid ~10 min; cache the CST/security tokens in
# Redis so we don't re-login (a slow, rate-limited POST /session) on every
# request. Slightly under the server-side expiry; a 401 triggers a re-login.
_SESSION_TTL = 8 * 60

LIVE_BASE = "https://api-capital.backend-capital.com"
DEMO_BASE = "https://demo-api-capital.backend-capital.com"


class CapitalComBroker(BrokerInterface):
    name = "capital_com"

    def __init__(
        self,
        api_key: str,
        identifier: str,
        password: str,
        *,
        demo: bool = True,
        timeout: float = 15.0,
    ) -> None:
        self.api_key = api_key
        self.identifier = identifier
        self.password = password
        self.is_paper = demo
        self.base_url = DEMO_BASE if demo else LIVE_BASE
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)
        self._cst: str | None = None
        self._security_token: str | None = None

    def _auth_headers(self) -> dict[str, str]:
        return {
            "CST": self._cst or "",
            "X-SECURITY-TOKEN": self._security_token or "",
            "Content-Type": "application/json",
        }

    @property
    def _session_key(self) -> str:
        digest = hashlib.sha256(
            f"{self.api_key}:{self.identifier}".encode()
        ).hexdigest()[:16]
        return f"capsess:{'demo' if self.is_paper else 'live'}:{digest}"

    async def connect(self, *, force: bool = False) -> None:
        """Open a Capital.com session, reusing cached tokens when possible.

        `force=True` skips the cache and performs a fresh login (used to recover
        from an expired/invalid cached session)."""
        if not force:
            try:
                cached = await get_redis().get(self._session_key)
            except Exception:
                cached = None
            if cached:
                data = json.loads(cached)
                self._cst = data.get("cst")
                self._security_token = data.get("sec")
                if self._cst and self._security_token:
                    return

        resp = await self._client.post(
            "/api/v1/session",
            headers={"X-CAP-API-KEY": self.api_key, "Content-Type": "application/json"},
            json={"identifier": self.identifier, "password": self.password},
        )
        resp.raise_for_status()
        self._cst = resp.headers.get("CST")
        self._security_token = resp.headers.get("X-SECURITY-TOKEN")
        logger.info("capital.com session opened", extra={"demo": self.is_paper})
        try:
            await get_redis().set(
                self._session_key,
                json.dumps({"cst": self._cst, "sec": self._security_token}),
                ex=_SESSION_TTL,
            )
        except Exception:
            pass

    async def _get(self, url: str, **kwargs) -> httpx.Response:
        """GET with the session headers; on 401/403 (expired cached session) it
        re-logs in once and retries, so a stale cache never surfaces as an error."""
        resp = await self._client.get(url, headers=self._auth_headers(), **kwargs)
        if resp.status_code in (401, 403):
            try:
                await get_redis().delete(self._session_key)
            except Exception:
                pass
            await self.connect(force=True)
            resp = await self._client.get(url, headers=self._auth_headers(), **kwargs)
        return resp

    async def get_balance(self) -> float:
        acc = await self.get_account()
        return float(acc.get("equity", 0.0))

    async def get_account(self) -> dict:
        """Full account snapshot from /accounts (equity, available & used margin,
        open P/L, currency) — for a realistic broker-style header."""
        resp = await self._get("/api/v1/accounts")
        resp.raise_for_status()
        accounts = resp.json().get("accounts", [])
        if not accounts:
            return {}
        a = accounts[0]
        bal = a.get("balance", {}) or {}
        equity = float(bal.get("balance", 0.0))        # account value
        available = float(bal.get("available", 0.0))   # free margin
        return {
            "equity": equity,
            "available": available,
            "used_margin": round(max(0.0, equity - available), 2),
            "deposit": float(bal.get("deposit", 0.0)),
            "profit_loss": float(bal.get("profitLoss", 0.0)),
            "currency": a.get("currency", ""),
        }

    async def get_price(self, symbol: str) -> float:
        resp = await self._get(f"/api/v1/markets/{symbol}")
        resp.raise_for_status()
        snap = resp.json().get("snapshot", {})
        bid, offer = snap.get("bid"), snap.get("offer")
        if bid and offer:
            return (float(bid) + float(offer)) / 2.0
        return float(bid or offer or 0.0)

    async def get_candles(
        self, symbol: str, resolution: str = "HOUR", limit: int = 200
    ) -> pd.DataFrame | None:
        """Fetch OHLC candles from the documented /prices endpoint."""
        resp = await self._get(
            f"/api/v1/prices/{symbol}",
            params={"resolution": resolution, "max": limit},
        )
        if resp.status_code >= 400:
            return None
        rows = resp.json().get("prices", [])
        if not rows:
            return None

        def mid(p):  # bid/ask -> mid
            bid, ask = p.get("bid"), p.get("ask")
            vals = [float(v) for v in (bid, ask) if v is not None]
            return sum(vals) / len(vals) if vals else None

        records = []
        for r in rows:
            o, h, l, c = (mid(r.get(k, {})) for k in
                          ("openPrice", "highPrice", "lowPrice", "closePrice"))
            if None in (o, h, l, c):
                continue
            records.append(
                {"open": o, "high": h, "low": l, "close": c,
                 "volume": float(r.get("lastTradedVolume", 0) or 0),
                 "ts": r.get("snapshotTimeUTC") or r.get("snapshotTime")}
            )
        if not records:
            return None
        df = pd.DataFrame(records)
        df.index = pd.to_datetime(df.pop("ts"), errors="coerce")
        return df[["open", "high", "low", "close", "volume"]]

    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> BrokerOrder:
        payload = {
            "epic": symbol,
            "direction": side,  # BUY | SELL
            "size": quantity,
        }
        if stop_loss is not None:
            payload["stopLevel"] = stop_loss
        if take_profit is not None:
            payload["profitLevel"] = take_profit
        resp = await self._client.post(
            "/api/v1/positions", headers=self._auth_headers(), json=payload
        )
        if resp.status_code >= 400:
            return BrokerOrder(
                "", symbol, side, quantity, 0.0, "REJECTED", reason=resp.text[:200]
            )
        deal_ref = resp.json().get("dealReference", "")
        return BrokerOrder(
            broker_order_id=deal_ref, symbol=symbol, side=side, quantity=quantity,
            price=await self.get_price(symbol), status="FILLED",
            stop_loss=stop_loss, take_profit=take_profit,
        )

    async def get_positions(self) -> list[BrokerPosition]:
        resp = await self._get("/api/v1/positions")
        resp.raise_for_status()
        out = []
        for item in resp.json().get("positions", []):
            pos = item.get("position", {})
            market = item.get("market", {})
            direction = pos.get("direction", "BUY")
            entry = float(pos.get("level", 0.0))
            size = float(pos.get("size", 0.0))
            cur = float(market.get("bid", entry))
            sign = 1 if direction == "BUY" else -1
            out.append(
                BrokerPosition(
                    symbol=market.get("epic", ""), side=direction, quantity=size,
                    entry_price=entry, current_price=cur,
                    unrealized_pnl=round((cur - entry) * size * sign, 2),
                    stop_loss=pos.get("stopLevel"), take_profit=pos.get("profitLevel"),
                )
            )
        return out

    async def close_position(self, symbol: str) -> BrokerOrder:
        # Capital.com closes by dealId; resolve the position first.
        positions = await self._client.get(
            "/api/v1/positions", headers=self._auth_headers()
        )
        positions.raise_for_status()
        deal_id = None
        for item in positions.json().get("positions", []):
            if item.get("market", {}).get("epic") == symbol:
                deal_id = item.get("position", {}).get("dealId")
                break
        if not deal_id:
            return BrokerOrder("", symbol, "", 0, 0, "REJECTED", reason="no position")
        resp = await self._client.delete(
            f"/api/v1/positions/{deal_id}", headers=self._auth_headers()
        )
        status = "FILLED" if resp.status_code < 400 else "REJECTED"
        return BrokerOrder(deal_id, symbol, "", 0, 0, status)

    async def aclose(self) -> None:
        await self._client.aclose()
