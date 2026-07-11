# RestaurantOS

> Restaurant management with inventory intelligence and preparation planning.

RestaurantOS turns every sale into an accurate ingredient forecast, a
preparation plan, a purchasing recommendation, and a waste report.

The current code is **Phase 0** of a four-phase rebuild — see
[../PHASES.md](../PHASES.md) for the full plan. Phase 0 makes the system
_truthful_: backend is the source of truth, the browser talks to it
through a real API, no fake numbers, no fake sync success.

---

## Stack

- **Frontend:** Next.js 15 (App Router) + React 19 + TypeScript + Tailwind + shadcn/ui
  - State: TanStack Query (server data) + Zustand (cart/UI only)
- **Backend:** FastAPI + SQLite (dev) / PostgreSQL (prod)
  - Forecasting: Prophet (lazy-loaded; the API boots without it)
  - Background work: a separate `worker.py` process

## Prerequisites

- Node.js 20+
- Python 3.10+ (3.11 recommended; tested on 3.12)
- npm 10+

## Quick start

```bash
# 1. Frontend deps
npm install --legacy-peer-deps

# 2. Backend deps (creates .venv if missing)
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate
pip install -r requirements.txt
# Optional: enable Prophet-based predictions
# pip install -r requirements-ml.txt
# Test deps:
pip install -r requirements-dev.txt
cd ..

# 3. Run the two processes
# Terminal 1 — backend on http://localhost:8000
cd backend
python run.py

# Terminal 2 — frontend on http://localhost:3000
cd ..
npm run dev

# Terminal 3 (optional) — background worker
cd backend
python worker.py
```

Open http://localhost:3000 in your browser. The Dashboard shows "—"
until the first order lands; that is intentional.

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

### Frontend (`restaurant-management-system/`)

| Command                | Purpose                                                 |
| ---------------------- | ------------------------------------------------------- |
| `npm run dev`          | Start the Next.js dev server.                           |
| `npm run build`        | Production build. Fails on TypeScript or ESLint errors. |
| `npm run start`        | Run the production build.                               |
| `npm run typecheck`    | `tsc --noEmit` — fails on any type error.               |
| `npm run lint`         | `next lint` — fails on any lint error.                  |
| `npm run test`         | Run Vitest unit tests.                                  |
| `npm run format:check` | Verify Prettier formatting.                             |
| `npm run format`       | Apply Prettier formatting.                              |

### Backend (`backend/`)

| Command                               | Purpose                                                            |
| ------------------------------------- | ------------------------------------------------------------------ |
| `python run.py`                       | Start the API (uvicorn with reload).                               |
| `python worker.py`                    | Start the background worker (heartbeat only in Phase 0).           |
| `python worker.py --once`             | Run a single tick and exit (smoke test).                           |
| `pytest -q`                           | Run the test suite.                                                |
| `pip install -r requirements.txt`     | Runtime deps.                                                      |
| `pip install -r requirements-ml.txt`  | Add Prophet + pandas + numpy (heavy; only needed for predictions). |
| `pip install -r requirements-dev.txt` | Add pytest + httpx for local testing.                              |

## End-to-end smoke test

```bash
# In one terminal:
cd backend && python run.py

# In another:
bash scripts/e2e-smoke.sh   # macOS / Linux
# or on Windows:
node scripts/e2e-smoke.cjs
```

The script creates a dish, an ingredient, places an order with an
`Idempotency-Key`, and verifies the server-side total matches the
authoritative dish price.

## Phase 0 contract — what is and isn't built

**Built and verified:**

- All dishes, ingredients, and orders flow through the FastAPI backend
- The browser is a thin client (TanStack Query); no localStorage-as-DB
- Server-side price, tax, and total calculation (client values are ignored)
- Idempotency-Key on order creation; duplicates return the original order
- `POST /api/orders` defaults to status `pending` (was `completed`)
- `update_ingredient_quantity` records the **delta** in the ledger
- Backend error handling preserves HTTP status codes (no more 404 → 500)
- `/api/health` actually checks the database
- `app/api/sync` (Next.js) returns 503 when the backend is unreachable
- DEMO_MODE banner and stub `POST /api/demo/seed` endpoint
- 28 tests across backend + frontend
- `next.config.mjs` has `ignoreBuildErrors` / `ignoreDuringBuilds` removed

**Intentionally not built in Phase 0:**

- Analytics page (the backend endpoint exists; the UI is a "no data" empty state)
- Reports / Predictions / Kitchen / Settings (removed from sidebar)
- Order state machine beyond `pending` (Phase 1)
- Inventory ledger beyond consumption + manual adjustment (Phase 1)
- Multi-tenant, supplier, payments, audit (Phase 3)

## Why does this matter?

The previous build looked alive on the dashboard but lied about
everything. A "revenue" number generated from random samples, a "low
stock" count that disagreed with the inventory page, a sync that
returned `200 ok` while the backend was off. Operators learned to
ignore the UI.

Phase 0 fixes that. Every number is real, every failure is visible, and
every screen agrees with every other screen.
