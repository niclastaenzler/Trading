# Deployment — GitHub Pages (frontend) + Render (backend)

This hosts the platform for real, all on free tiers, with auto-deploy on `git push`:

```
  Browser
     │  https
     ▼
  GitHub Pages  ──── static Next.js (this repo, /trading) ────┐
     │  REST + WebSocket (https/wss)                          │ build-time:
     ▼                                                        │ NEXT_PUBLIC_API_URL
  Render  ──────── FastAPI (Docker, backend/) ────────────────┘
     ├── Postgres  → Supabase  (project ai-trading-platform, already created)
     └── Redis     → Upstash   (free)
```

> GitHub Pages can only serve **static files** — it cannot run Python/Redis/DB.
> So the frontend lives on Pages and the backend on Render; they talk over HTTPS.

---

## 1. Database — Supabase (already provisioned)

The project `ai-trading-platform` (`cddgxnbyhkrhehilitzz`, eu-central-1) already
has the schema applied. Get its connection string:

Supabase → Project → **Connect** → "Session pooler" (IPv4, works from Render):

```
postgresql+asyncpg://postgres.cddgxnbyhkrhehilitzz:[YOUR-DB-PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:5432/postgres
```

Keep this as your `DATABASE_URL` (note the `+asyncpg`).

## 2. Redis — Upstash (free)

1. https://upstash.com → create a **Redis** database (region close to Render).
2. Copy the **`rediss://`** URL (TLS) → this is your `REDIS_URL`.

## 3. Backend — Render

1. Generate a Fernet key for `ENCRYPTION_KEY`:
   ```bash
   python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
   ```
2. Render Dashboard → **New → Blueprint** → select this repo. It reads
   [`render.yaml`](render.yaml) and creates the `ai-trading-backend` service.
3. In the service's **Environment**, set the `sync:false` secrets:
   | Key | Value |
   |---|---|
   | `ENCRYPTION_KEY` | the Fernet key from step 1 |
   | `DATABASE_URL` | the Supabase pooler URL (step 1) |
   | `REDIS_URL` | the Upstash URL (step 2) |
   | `CORS_ORIGINS` | `https://niclastaenzler.github.io` (origin only, no path) |
4. Deploy. When live, note the URL, e.g. `https://ai-trading-backend.onrender.com`.
   Check `https://…onrender.com/health` returns `{"status":"ok"}`.

## 4. Frontend — GitHub Pages

1. Repo **Settings → Pages → Source = "GitHub Actions"**.
2. Repo **Settings → Secrets and variables → Actions → Variables** → add:
   | Variable | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | your Render URL, e.g. `https://ai-trading-backend.onrender.com` |
   | `PAGES_BASE_PATH` | `/trading` (only if your repo is named `trading`) |
3. Run the **"Deploy frontend to GitHub Pages"** workflow (Actions tab →
   Run workflow), or just push to the branch.
4. Your site goes live at:
   ```
   https://niclastaenzler.github.io/trading/
   ```

Open it, register (first account = **owner**), and you're in — paper mode,
auto-trading off, talking to the Render backend.

---

## Important notes (free tier)

- **Cold start**: Render free services sleep when idle; the first request after
  a pause takes ~30–60 s. Normal for free hosting.
- **Scheduler is OFF** on free (`ENABLE_SCHEDULER=0`) because a sleeping service
  can't run background cycles. Options: trigger `POST /api/trading/run-cycle`
  from an external cron (e.g. GitHub Actions schedule, cron-job.org), or use an
  always-on (paid) Render instance and set `ENABLE_SCHEDULER=1`.
- **Secrets**: never commit `ENCRYPTION_KEY` / DB / Redis URLs — set them only in
  Render. The production startup check refuses to boot with insecure defaults.
- **Changing the API URL** requires a **frontend rebuild** (it's baked in at
  build time) — re-run the Pages workflow after changing `NEXT_PUBLIC_API_URL`.
- After merging to `main`, update the `branch:` in `render.yaml` and the trigger
  branch in the Pages workflow if you want deploys to track `main`.
