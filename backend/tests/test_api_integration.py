"""End-to-end API tests through the ASGI app (SQLite + fakeredis)."""


async def test_health(client):
    res = await client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


async def test_register_first_user_is_owner(client):
    res = await client.post(
        "/api/auth/register", json={"email": "a@test.io", "password": "secret12"}
    )
    assert res.status_code == 201
    assert res.json()["role"] == "owner"

    # Second account becomes a viewer (single-user focus).
    res2 = await client.post(
        "/api/auth/register", json={"email": "b@test.io", "password": "secret12"}
    )
    assert res2.json()["role"] == "viewer"


async def test_login_and_me(owner_client):
    res = await owner_client.get("/api/auth/me")
    assert res.status_code == 200
    assert res.json()["email"] == "owner@test.io"


async def test_default_config_is_conservative(owner_client):
    res = await owner_client.get("/api/config")
    cfg = res.json()["config"]
    assert cfg["trading"]["risk_per_trade_pct"] <= 1.0
    assert cfg["compliance"]["compliance_mode"] is True
    assert res.json()["auto_trading_enabled"] is False


async def test_config_update_clamps_reckless_values(owner_client):
    current = (await owner_client.get("/api/config")).json()["config"]
    current["trading"]["risk_per_trade_pct"] = 2.0  # reckless
    current["automation"]["max_trades_per_hour"] = 20
    res = await owner_client.put("/api/config", json={"config": current})
    assert res.status_code == 200
    saved = res.json()["config"]
    # Compliance envelope clamps to safe ceilings.
    assert saved["trading"]["risk_per_trade_pct"] == 1.0
    assert saved["automation"]["max_trades_per_hour"] <= 6


async def test_kill_switch_blocks_auto_trading(owner_client):
    await owner_client.post("/api/config/kill-switch?activate=true")
    res = await owner_client.post(
        "/api/config/automation", json={"auto_trading_enabled": True}
    )
    body = res.json()
    assert body["kill_switch_active"] is True
    assert body["auto_trading_enabled"] is False  # cannot enable while killed


async def test_backtest_returns_metrics(owner_client):
    res = await owner_client.post(
        "/api/backtest", json={"symbol": "EURUSD", "bars": 300}
    )
    assert res.status_code == 200
    data = res.json()
    for key in ("total_return_pct", "sharpe", "sortino", "profit_factor", "win_rate"):
        assert key in data


async def test_run_cycle_executes_pipeline(owner_client):
    res = await owner_client.post("/api/trading/run-cycle")
    assert res.status_code == 200
    body = res.json()
    assert body["cycle"] == "complete"
    assert isinstance(body["results"], list)


async def test_performance_shape(owner_client):
    res = await owner_client.get("/api/trades/performance")
    assert res.status_code == 200
    data = res.json()
    for key in ("equity", "profit_factor", "avg_win", "avg_loss", "equity_curve"):
        assert key in data


async def test_performance_with_closed_trades(owner_client):
    """Regression: performance must handle CLOSED trades whose closed_at is
    naive (SQLite) without raising on the tz-aware 'today' comparison."""
    from datetime import datetime, timezone

    from app.models.trade import Trade

    async with owner_client.test_sessionmaker() as s:
        s.add_all([
            Trade(user_id=1, symbol="EURUSD", side="BUY", quantity=1000,
                  entry_price=1.10, exit_price=1.11, status="CLOSED",
                  mode="paper", pnl=10.0, closed_at=datetime.now(timezone.utc)),
            Trade(user_id=1, symbol="GBPUSD", side="SELL", quantity=1000,
                  entry_price=1.25, exit_price=1.26, status="CLOSED",
                  mode="paper", pnl=-5.0, closed_at=datetime.now(timezone.utc)),
        ])
        await s.commit()

    res = await owner_client.get("/api/trades/performance")
    assert res.status_code == 200
    data = res.json()
    assert data["total_trades"] == 2
    assert data["total_pnl"] == 5.0
    assert data["profit_factor"] == 2.0  # 10 / 5
    assert len(data["equity_curve"]) == 2
