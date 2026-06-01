# AI Trading Platform (Compliant MVP)

A **single-user**, web-based automated trading platform that combines an AI model,
pattern recognition and a trend filter — wrapped in **mandatory risk and
compliance safeguards** so it stays within broker rules, API limits and EU
expectations for personal automated trading.

> ⚠️ **Personal use only.** This is not investment advice and not a
> multi-user/fund-management product. Trading carries risk of loss. The system
> **defaults to paper trading**; live trading requires explicit, deliberate
> opt-in.

---

## ✨ Highlights

- **Compliance-first by design** — official broker APIs only, rate limiting,
  enforced trade cadence (anti-HFT), trading-session windows, volatility halts,
  a global **kill switch**, and a full **audit log**.
- **Conservative safe defaults** — paper mode, semi-auto confirmation, ≤1% risk
  per trade, mandatory stop-loss, daily loss + drawdown cut-offs. Reckless
  configs are **clamped or rejected** by a validated config envelope.
- **Explainable signals** — every trade records the AI / pattern / trend
  contributions that produced it.
- **Backtesting** (Sharpe, Sortino, profit factor, avg win/loss, drawdown) that
  reuses the *same* signal + risk code as live trading.
- **Real market data** via the broker's documented candles endpoint, with a
  deterministic synthetic fallback for offline demo/backtest.
- **Automatic position management** — open positions are monitored each cycle
  and closed when their stop-loss / take-profit is hit.
- **Honest AI evaluation** — chronological train/test split + walk-forward
  out-of-sample scoring (no in-sample self-deception).
- **Paper + live brokers** behind one interface (paper default, Capital.com
  adapter included, TradingView webhook bridge).

---

## 🏗️ Architecture

```
┌─────────────┐      WebSocket / REST      ┌──────────────────────────────┐
│  Next.js UI │ ◀────────────────────────▶ │  FastAPI backend              │
│ dashboard / │                            │                               │
│ config /    │                            │  ┌──────────── trading_engine │
│ trades /    │                            │  │  signal_engine             │
│ backtest    │                            │  │   ├─ ai_engine             │
└─────────────┘                            │  │   ├─ patterns / indicators │
                                           │  │   └─ trend filter          │
                                           │  ├─ risk_manager  (mandatory) │
                                           │  ├─ compliance_guard (gate)   │
                                           │  └─ broker_service (paper/    │
                                           │        capital.com / TV hook) │
                                           └───────┬───────────────┬───────┘
                                                   │               │
                                           ┌───────▼──────┐ ┌──────▼───────┐
                                           │ PostgreSQL   │ │ Redis        │
                                           │ users/trades │ │ signals/cache│
                                           │ /configs/    │ │ rate limits  │
                                           │  audit_logs  │ │ pub/sub bus  │
                                           └──────────────┘ └──────────────┘
```

**Decision → execution pipeline** (per symbol, per cycle):

1. `signal_engine` fuses AI prediction + pattern signals + trend confirmation;
   trades only when the combined **confidence threshold** is met.
2. `risk_manager` sizes the position from risk-%, attaches a **mandatory stop**
   and target, and validates (max positions, daily loss, drawdown).
3. `compliance_guard` gates on rate limits, trade cadence, session window,
   volatility and the kill switch.
4. `broker_service` executes (paper by default; live only when opted in).
5. Everything is persisted (orders/trades) and **audit-logged**, then pushed to
   the UI over WebSocket and optionally to Telegram.

A background **scheduler** ticks every 60s and runs cycles for accounts with
auto-trading enabled. The compliance guard enforces real cadence, so a frequent
tick can never become high-frequency trading.

---

## 📁 Project structure

```
.
├── docker-compose.yml          # db + redis + backend + frontend
├── .env.example                # all configuration / secrets
├── backend/
│   ├── app/
│   │   ├── main.py             # FastAPI app, lifespan, prod safety checks
│   │   ├── config.py           # env settings
│   │   ├── core/               # security (JWT), encryption, db, redis, logging
│   │   ├── models/             # users, trading_configs, orders, trades, audit_logs
│   │   ├── schemas/            # pydantic request/response models
│   │   ├── api/routes/         # auth, config, trading, trades, backtest, webhooks, ws
│   │   ├── analysis/           # indicators (RSI/MACD/EMA/ATR), patterns
│   │   ├── services/
│   │   │   ├── config_defaults.py   # ⭐ validated config + safe envelope
│   │   │   ├── signal_engine.py     # AI + pattern + trend fusion
│   │   │   ├── ai_engine.py         # example ML model (+ heuristic fallback)
│   │   │   ├── risk_manager.py      # sizing, stops, validation (mandatory)
│   │   │   ├── compliance_guard.py  # the trade gate (anti-HFT, sessions, etc.)
│   │   │   ├── rate_limiter.py      # Redis sliding-window limiter
│   │   │   ├── trading_engine.py    # orchestration
│   │   │   ├── scheduler.py         # periodic cycle runner
│   │   │   ├── broker/              # broker_interface + paper + capital.com + factory
│   │   │   ├── market_data.py       # OHLCV (synthetic for demo/backtest)
│   │   │   └── notifications.py     # Telegram alerts
│   │   └── backtest/engine.py
│   ├── migrations/             # Alembic (async) — versioned schema
│   ├── scripts/train_model.py  # train + walk-forward evaluation
│   └── tests/                  # unit (logic) + integration (ASGI/SQLite/fakeredis)
├── frontend/                   # Next.js (dashboard, config panel, trades, backtest)
│   └── app/components/EquityChart.tsx   # TradingView Lightweight-Charts
└── .github/workflows/ci.yml    # CI: backend pytest + frontend build
```

---

## ⚙️ Configuration system

All trading behaviour is user-configurable and **validated on every write**
(`backend/app/services/config_defaults.py`). Groups: **Trading**, **Strategy**,
**Automation**, **Risk**, **Compliance** — editable from the UI's *Configuration*
page or `PUT /api/config`.

**Guardrails (cannot be bypassed):**

- `require_stop_loss` is always enforced (rejected if disabled with compliance
  mode off; silently re-enabled with it on).
- Hard numeric caps via Pydantic (`risk_per_trade_pct ≤ 2`, etc.).
- `compliance_mode` (default **on**) clamps risk %, position count, trade
  frequency, API rate and daily-loss limit to conservative ceilings.
- Cooldown can never be shorter than the compliance min-delay between trades.
- The **kill switch** disables auto-trading and blocks re-enabling until cleared.

Default config is deliberately conservative (paper, semi-auto, 0.5% risk,
ATR stop, 2:1 R:R, ≤2 trades/hour, 5-min cooldown, full audit logging).

---

## ⚖️ Compliance notes

- **Official APIs only.** The Capital.com adapter uses the documented public
  REST API (`open-api.capital.com`). No scraping, no reverse engineering.
- **Rate limiting & retries** via a Redis-backed sliding-window limiter shared
  across processes.
- **Anti-HFT**: enforced min delay + cooldown between trades and max
  trades/hour/day.
- **Auditability**: every order, block and config change is written to
  `audit_logs` and emitted as structured JSON to stdout.
- **Single-user**: the first registered account is the `owner`; only the owner
  can trade or change config.

---

## 🚀 Quick start (Docker)

```bash
cp .env.example .env
# Generate secrets:
python -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
# Paste both into .env, then:

docker compose up --build
```

- Frontend: <http://localhost:3000>
- API docs (Swagger): <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>

Register the first account in the UI (it becomes the **owner**). You start in
**paper mode** with auto-trading **off**.

### Using Supabase Postgres instead of the bundled DB

A Supabase project (`ai-trading-platform`, region `eu-central-1`) has been
provisioned with the schema already applied. To point the backend at it, set in
`.env` (paste your project DB password):

```
DATABASE_URL=postgresql+asyncpg://postgres:[PASSWORD]@db.cddgxnbyhkrhehilitzz.supabase.co:5432/postgres
```

> **Security:** RLS is enabled (deny-all) on all tables because the backend
> connects as the `postgres` role over a direct connection and does **not** use
> the public anon/PostgREST surface. Do not expose the anon key to the browser
> for these tables.

---

## 🧑‍💻 Local development (without Docker)

**Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export $(grep -v '^#' ../.env | xargs)   # or set vars manually
uvicorn app.main:app --reload
```

**Frontend**

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

**Database migrations (production)**

`init_models()` auto-creates tables for first-run/dev. For production use
Alembic (the DB URL is read from your environment):

```bash
cd backend && alembic upgrade head
```

**Tests** (37: unit logic + ASGI integration, no external services needed)

```bash
cd backend && pytest -q
```

**Train the example AI model** (optional — a heuristic works without it):

```bash
cd backend && python -m scripts.train_model --bars 3000
```

---

## 🔌 Enabling a live broker (deliberate opt-in)

1. `POST /api/trades/broker` with `{ "broker": "capital_com", "api_key": "...",
   "identifier": "...", "password": "...", "demo": true }`. Credentials are
   **encrypted at rest** (Fernet).
2. Keep `demo: true` until you have validated behaviour in the broker's demo
   environment.
3. Enable auto-trading (`POST /api/config/automation`) and ensure the kill
   switch is clear. Risk + compliance gates still apply to every order.

---

## 🔬 Edge research harness

`backend/research/` is a standalone, **honest** quant-research pipeline to search
for and evaluate a statistical edge: no-lookahead features (+ optional
news/sentiment), baseline→logistic→gradient-boosting models, **walk-forward**
validation (no random split), significance testing (binomial, t-test, and
Monte-Carlo **vs random**), and leverage analysis that only runs once an edge is
proven. It loads **current** data (Binance/yfinance/broker) where the network
permits, and ships known-truth synthetic controls to validate the detector
itself. See [`backend/research/README.md`](backend/research/README.md) for the
methodology, how to run on live data, and the honest findings (TL;DR: daily
single-asset direction shows **no robust edge** — as expected).

## 🤖 Bonus integrations

- **TradingView**: point an alert webhook at `POST /api/webhooks/tradingview`
  with body `{"secret": "...", "symbol": "EURUSD", "side": "BUY",
  "confidence": 0.8}`. External signals pass through the **same** risk +
  compliance pipeline.
- **Telegram**: set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` for trade
  alerts (no-op if unset).

---

## 🔐 Security

- Passwords hashed with bcrypt; JWT access tokens.
- Broker credentials encrypted with Fernet (`ENCRYPTION_KEY`).
- Production startup **refuses to boot** with insecure default secrets.
- Role-based access (owner vs viewer); only the owner can trade/configure.
- Structured, auditable logging.

---

## ⚠️ Disclaimer

For educational/personal use. No warranty. You are responsible for complying
with your broker's terms and applicable regulations in your jurisdiction, and
for any financial outcomes.
