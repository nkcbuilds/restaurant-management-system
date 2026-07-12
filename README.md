# RestaurantOS

> Restaurant management with inventory intelligence and preparation planning.

RestaurantOS turns every sale into an accurate ingredient forecast, a
preparation plan, a purchasing recommendation, and a waste report.

Phases 0–3 of the rebuild are complete — see
[../PHASES.md](../PHASES.md) for the full plan and per-phase evidence.
The system is server-driven, testable, and Phase 3 production-scaffolded.

---

## Stack

- **Frontend:** Next.js 15 (App Router) + React 19 + TypeScript + Tailwind + shadcn/ui
  - State: TanStack Query (server data) + Zustand (cart/UI only)
- **Backend:** FastAPI + SQLite (dev) / PostgreSQL (prod)
  - Forecasting: 3 named baselines + Prophet (lazy-loaded; API boots without it)
  - Background work: a separate `worker.py` process
- **Tests:** 84 backend (pytest) + 25 frontend (vitest) + 9 e2e (node)
- **CI:** GitHub Actions + a Makefile mirror of the same gates

## Prerequisites

- Node.js 20+
- Python 3.10+ (3.11 recommended; tested on 3.12)
- npm 10+
- GNU make (or `make` from MSYS2 / Git Bash on Windows). No `make`? Use `scripts\bootstrap.ps1` instead.

## Quick start

```bash
git clone <repo>
cd restaurant-management-system

make setup     # installs frontend + backend deps (creates backend/.venv)
make test      # runs every quality gate
make dev       # starts backend (8000) + frontend (3000) in parallel
```

Open http://localhost:3000 in your browser. The Dashboard shows `—`
until the first order lands; that is intentional.

On Windows without `make`:

```powershell
.\scripts\bootstrap.ps1     # one-time install
.\scripts\test.ps1         # run every quality gate
npm run dev                 # frontend (separate terminal)
.\backend\.venv\Scripts\python.exe backend\run.py   # backend
```

### Manual fallback (no `make`)

```bash
# 1. Frontend deps
npm install --legacy-peer-deps

# 2. Backend deps (creates .venv if missing)
cd backend
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cd ..

# 3. Run the two processes
# Terminal 1 — backend on http://localhost:8000
cd backend && python run.py

# Terminal 2 — frontend on http://localhost:3000
cd .. && npm run dev

# Terminal 3 (optional) — background worker
cd backend && python worker.py
```

## Environment variables

Copy `.env.example` to `.env.local` in `restaurant-management-system/`.

| Variable                             | Default                                       | Notes                                                                                                                                                 |
| ------------------------------------ | --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NEXT_PUBLIC_API_URL`                | `http://localhost:8000`                       | Base URL of the FastAPI backend. The frontend calls `${API_URL}/api/...`. **Do not** set this to `http://localhost:3000` (that is the frontend port). |
| `NEXT_PUBLIC_DEMO_MODE`              | `false`                                       | When `true`, the UI shows a persistent "demo restaurant" banner. The backend also exposes `POST /api/demo/seed` (see `backend/core/__init__.py`).     |
| `RESTAURANT_DB_PATH`                 | `restaurant.db`                               | Backend SQLite file path.                                                                                                                             |
| `RESTAURANT_TAX_RATE`                | `0.0`                                         | Default tax rate (fraction, e.g. `0.05` for 5%). Applied server-side.                                                                                 |
| `RESTAURANT_REQUIRE_IDEMPOTENCY_KEY` | `true`                                        | If true, `POST /api/orders` requires an `Idempotency-Key` header.                                                                                     |
| `CORS_ALLOW_ORIGINS`                 | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated list of allowed origins.                                                                                                              |

## Available scripts

### `make` shortcuts (preferred on POSIX or Git Bash)

Run `make help` to see every target. The common ones:

| Command         | What it does                                                   |
| --------------- | -------------------------------------------------------------- |
| `make help`     | List every available target with descriptions.                 |
| `make setup`    | Install frontend + backend deps (idempotent; creates `.venv`). |
| `make test`     | Run typecheck, lint, format:check, vitest, pytest.             |
| `make e2e`      | Boot backend, run the 9-step e2e smoke, tear down.             |
| `make build`    | Production build of the frontend.                              |
| `make dev`      | Run backend + frontend together (Ctrl-C stops both).           |
| `make backend`  | Run only the FastAPI backend on :8000.                         |
| `make frontend` | Run only the Next.js dev server on :3000.                      |
| `make worker`   | Run the background worker process.                             |
| `make stop`     | Kill any leftover uvicorn / next dev processes.                |
| `make lint`     | Run every linter (next lint + ruff).                           |
| `make format`   | Auto-format frontend (prettier) and backend (ruff).            |
| `make ci`       | What `.github/workflows/ci.yml` runs, but locally.             |
| `make clean`    | Remove build artifacts, caches, dev DB.                        |

### Frontend (`restaurant-management-system/`)

| Command                | Purpose                                                 |
| ---------------------- | ------------------------------------------------------- |
| `npm run dev`          | Start the Next.js dev server.                           |
| `npm run build`        | Production build. Fails on TypeScript or ESLint errors. |
| `npm run start`        | Run the production build.                               |
| `npm run typecheck`    | `tsc --noEmit` — fails on any type error.               |
| `npm run lint`         | `next lint` — fails on any lint error.                  |
| `npm test`             | Run Vitest unit tests.                                  |
| `npm run format:check` | Verify Prettier formatting.                             |
| `npm run format`       | Apply Prettier formatting.                              |

### Backend (`backend/`)

| Command                                | Purpose                                                            |
| -------------------------------------- | ------------------------------------------------------------------ |
| `python run.py`                        | Start the API (uvicorn with reload).                               |
| `python worker.py`                     | Start the background worker (heartbeat only in Phase 0).           |
| `python worker.py --once`              | Run a single tick and exit (smoke test).                           |
| `pytest -q`                            | Run the test suite.                                                |
| `ruff check .` / `ruff format .`       | Lint / format the backend (optional dep).                          |
| `pip install -r requirements.txt`      | Runtime deps.                                                      |
| `pip install -r requirements-ml.txt`   | Add Prophet + pandas + numpy (heavy; only needed for predictions). |
| `pip install -r requirements-dev.txt`  | Add pytest + httpx for local testing.                              |
| `pip install -r requirements-lint.txt` | Add ruff for local linting.                                        |

## End-to-end smoke test

The smoke test boots the backend, runs a 9-step integration check
(dish/ingredient/order creation, server-priced totals, idempotency,
stock-overflow rejection), and tears the backend down.

```bash
make e2e                             # POSIX / Git Bash
# or, without make:
bash scripts/e2e.sh                  # POSIX
powershell -File scripts/e2e.ps1     # Windows PowerShell

# Or against an already-running backend:
node scripts/e2e-smoke.cjs
```

The script creates a dish, an ingredient, places an order with an
`Idempotency-Key`, and verifies the server-side total matches the
authoritative dish price.

## What's built (Phases 0–3)

**Phase 0 — system is truthful**

- All dishes, ingredients, and orders flow through the FastAPI backend
- The browser is a thin client (TanStack Query); no localStorage-as-DB
- Server-side price, tax, and total calculation (client values are ignored)
- Idempotency-Key on order creation; duplicates return 200 with the original order
- `/api/health` actually checks the database and returns 503 on outage
- `app/api/sync` (Next.js) returns 503 when the backend is unreachable
- `update_ingredient_quantity` records the **delta** in the ledger
- Backend error handling preserves HTTP status codes (no more 404 → 500)
- `next.config.mjs` has `ignoreBuildErrors` / `ignoreDuringBuilds` removed
- DEMO_MODE banner and stub `POST /api/demo/seed` endpoint

**Phase 1 — real operational loop**

- Full 8-state order lifecycle (`draft → submitted → accepted → preparing → ready → served → completed` + `cancelled`) with server-enforced transitions
- Kitchen tickets page that auto-refreshes every 10s
- Waste, stock-count, and variance-report endpoints
- `X-User-Role` header RBAC: `cashier < kitchen < inventory < manager < owner`

**Phase 2 — trustworthy forecasting**

- 3 named baselines (`same-weekday`, `moving-average`, `recent-weighted`)
- Backtester that walks history forward and reports MAE / WAPE / bias / stockout-rate / waste per (dish, period)
- Predictions carry `model_used`, `model_confidence`, `data_sufficiency`, low/high range, and a human-readable reason
- `GET /api/prep-plan` and `GET /api/purchase-recommendations`

**Phase 3 — commercial readiness scaffolding**

- Suppliers + Purchase Orders (weighted-average cost on receive)
- Payments with idempotency and split-tender support
- Offline POS outbox with auto-flush on browser `online` event
- Audit log + minimal Prometheus `/metrics`

**Tests + CI**

- 84 backend tests (pytest) + 25 frontend tests (vitest) + 9 e2e checks
- GitHub Actions matrix (Node 20, Python 3.10/3.11/3.12)
- A Makefile that mirrors every CI gate locally

**Intentionally not built (Phase 4+):**

- Multi-tenant `restaurant_id` on every operational table
- Real payment-provider webhooks (Razorpay / Stripe)
- Discount codes + order modifiers
- Service worker + IndexedDB outbox (localStorage fallback works today)
- Alembic for proper migrations (in-place `_ensure_column` is Phase 0–3)
- PostgreSQL + `pg_dump` cron
- Tables / floor plans for sit-down restaurants
- Generated TypeScript client from FastAPI's OpenAPI schema
- Structured JSON logging + Sentry integration
