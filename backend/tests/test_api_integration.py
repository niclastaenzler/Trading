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


async def test_registration_requires_invite_code_when_configured(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "registration_invite_code", "let-me-in")
    # Missing/wrong code is rejected.
    bad = await client.post(
        "/api/auth/register", json={"email": "x@test.io", "password": "pw123456"}
    )
    assert bad.status_code == 403
    # Correct code is accepted.
    good = await client.post(
        "/api/auth/register",
        json={"email": "x@test.io", "password": "pw123456", "invite_code": "let-me-in"},
    )
    assert good.status_code == 201


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


async def test_config_update_is_user_controlled(owner_client):
    current = (await owner_client.get("/api/config")).json()["config"]
    current["trading"]["risk_per_trade_pct"] = 3.0
    current["automation"]["max_trades_per_hour"] = 30
    current["trading"]["max_open_positions"] = 15
    res = await owner_client.put("/api/config", json={"config": current})
    assert res.status_code == 200
    saved = res.json()["config"]
    # Numeric limits are user-controlled now — preserved, not clamped.
    assert saved["trading"]["risk_per_trade_pct"] == 3.0
    assert saved["automation"]["max_trades_per_hour"] == 30
    assert saved["trading"]["max_open_positions"] == 15
    # The one non-negotiable invariant remains: stops are mandatory.
    assert saved["risk"]["require_stop_loss"] is True


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


async def test_market_universe(owner_client):
    res = await owner_client.get("/api/market/universe")
    assert res.status_code == 200
    groups = res.json()["groups"]
    assert "forex" in groups and "commodities" in groups and "stocks" in groups


async def test_market_scan_ranks_opportunities(owner_client):
    res = await owner_client.get("/api/trading/scan")
    assert res.status_code == 200
    opps = res.json()["opportunities"]
    assert isinstance(opps, list)
    for o in opps:
        assert "symbol" in o and "confidence" in o and "actionable" in o


async def test_research_edge_verdict(owner_client):
    res = await owner_client.get("/api/research/edge?symbol=EURUSD&timeframe=1d&bars=900")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert isinstance(data["has_edge"], bool)
    assert "recommendations" in data and "feature_importance" in data


async def test_model_status_and_training(owner_client):
    # Initially no trained model status fields still present.
    res = await owner_client.get("/api/research/model")
    assert res.status_code == 200
    assert "is_trained" in res.json()

    # Train a small pooled model on synthetic data (paper broker).
    tr = await owner_client.post("/api/research/train?bars=300&max_symbols=3")
    assert tr.status_code == 200
    data = tr.json()
    assert data.get("ok") is True
    assert data["instruments"] >= 1
    assert len(data["feature_importance"]) > 0

    # Status now reports a trained model with persisted feature importance.
    st = await owner_client.get("/api/research/model")
    assert st.json()["is_trained"] is True
    assert len(st.json()["feature_importance"]) > 0


async def test_explain_reasoning(owner_client):
    res = await owner_client.get("/api/trading/explain?symbol=EURUSD")
    assert res.status_code == 200
    d = res.json()
    assert "decision_chain" in d and len(d["decision_chain"]) == 3
    assert "regime" in d and "confidence" in d and "edge_score" in d
    assert "action" in d


async def test_candles_report_data_source(owner_client):
    res = await owner_client.get("/api/market/candles?symbol=EURUSD&timeframe=1h&bars=120")
    assert res.status_code == 200
    data = res.json()
    assert "source" in data and "live" in data
    # Paper broker has no candle feed -> synthetic fallback, flagged honestly.
    assert data["source"] == "synthetic" and data["live"] is False
    assert len(data["candles"]) > 0
    # Strictly ascending unique timestamps (chart requirement).
    times = [c["time"] for c in data["candles"]]
    assert times == sorted(times) and len(times) == len(set(times))


async def test_config_exposes_edge_settings(owner_client):
    res = await owner_client.get("/api/config")
    cfg = res.json()["config"]
    assert "edge" in cfg and "min_edge_score" in cfg["edge"]
    assert "confidence_scaled_sizing" in cfg["risk"]


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
