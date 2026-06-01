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

import httpx

from app.core.logging_config import get_logger
from app.services.broker.broker_interface import (
    BrokerInterface,
    BrokerOrder,
    BrokerPosition,
)

logger = get_logger("broker.capital_com")

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

    async def connect(self) -> None:
        resp = await self._client.post(
            "/api/v1/session",
            headers={"X-CAP-API-KEY": self.api_key, "Content-Type": "application/json"},
            json={"identifier": self.identifier, "password": self.password},
        )
        resp.raise_for_status()
        self._cst = resp.headers.get("CST")
        self._security_token = resp.headers.get("X-SECURITY-TOKEN")
        logger.info("capital.com session opened", extra={"demo": self.is_paper})

    async def get_balance(self) -> float:
        resp = await self._client.get("/api/v1/accounts", headers=self._auth_headers())
        resp.raise_for_status()
        accounts = resp.json().get("accounts", [])
        if not accounts:
            return 0.0
        return float(accounts[0].get("balance", {}).get("available", 0.0))

    async def get_price(self, symbol: str) -> float:
        resp = await self._client.get(
            f"/api/v1/markets/{symbol}", headers=self._auth_headers()
        )
        resp.raise_for_status()
        snap = resp.json().get("snapshot", {})
        bid, offer = snap.get("bid"), snap.get("offer")
        if bid and offer:
            return (float(bid) + float(offer)) / 2.0
        return float(bid or offer or 0.0)

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
        resp = await self._client.get("/api/v1/positions", headers=self._auth_headers())
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
