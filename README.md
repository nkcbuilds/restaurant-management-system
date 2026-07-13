# RestaurantOS

> Restaurant management with inventory intelligence and preparation planning.

RestaurantOS turns every sale into an accurate ingredient forecast, a
preparation plan, a purchasing recommendation, and a waste report.

**Honest by design.** Every number on every screen is real, estimated, or
labelled. Killing the backend never makes the UI claim success. Two devices
always see the same data because the backend is the single source of truth.

---

## At a glance

- **Frontend:** Next.js 15 (App Router) + React 19 + TypeScript + Tailwind + shadcn/ui
- **Backend:** FastAPI + SQLite (dev) / PostgreSQL (prod)
- **Forecasting:** 3 named baselines + Prophet (lazy-loaded; API boots without it)
- **Background work:** a separate `worker.py` process
- **Tests:** 84 backend (pytest) + 25 frontend (vitest) + 9-step e2e smoke
- **Quality gates:** TypeScript strict + ESLint + Ruff + Prettier; all run by `make test`
- **Reproducible:** `make setup && make test && make e2e` works from a fresh clone (no external CI required)

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the system design, and
[`docs/PHASES.md`](docs/PHASES.md) for the rebuild history.

---

## Quick start

### With `make` (POSIX, macOS, Linux, Git Bash on Windows)

```bash
git clone <repo>
cd restaurant-management-system

make setup     # installs frontend + backend deps (creates backend/.venv)
make test      # runs every quality gate
make dev       # starts backend (8000) + frontend (3000) in parallel
```

Open http://localhost:3000 in your browser. The Dashboard shows `—` until
the first order lands; that is intentional.

### About CI

This project does **not** have a GitHub Actions workflow. The `Makefile`
is the single source of truth: `make test && make e2e` on a fresh clone
is the same set of gates that any CI would run. To add CI later (e.g.
if you open-source the project and want PRs gated), add a thin
workflow at `.github/workflows/ci.yml` that calls `make ci` — the
Makefile already exposes that target.

### Without `make` (Windows PowerShell)

```powershell
git clone <repo>
cd restaurant-management-system

.\scripts\bootstrap.ps1     # one-time install
.\scripts\test.ps1         # run every quality gate
npm run dev                 # frontend (separate terminal)
.\backend\.venv\Scripts\python.exe backend\run.py   # backend
```

### Manual fallback (no tooling wrappers)

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

---

## What does the app do?

| Page        | URL            | What it shows                                                                                |
| ----------- | -------------- | -------------------------------------------------------------------------------------------- |
| Dashboard   | `/`            | Live revenue, orders, low-stock, and a sync-status badge. Shows `—` until data exists.       |
| Inventory   | `/inventory`   | Dishes + recipes + ingredient stock. Inline quantity edits. Low-stock banner.                |
| Orders      | `/orders`      | POS cart, server-priced checkout, recent order history. Caches offline when backend is down. |
| Kitchen     | `/kitchen`     | Live ticket queue, polls every 10s, one-click lifecycle advance (accept → preparing → …).    |
| Predictions | `/predictions` | Demand forecast per (dish, period), backtest table, prep plan, reorder list.                 |

Sidebar badges are live: low-stock count from `/api/ingredients`,
open-kitchen count from `/api/kitchen/tickets`.

---

## Environment variables

Copy `.env.example` to `.env.local` at the project root.

| Variable                             | Default                                       | Notes                                                                                                                                                 |
| ------------------------------------ | --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NEXT_PUBLIC_API_URL`                | `http://localhost:8000`                       | Base URL of the FastAPI backend. The frontend calls `${API_URL}/api/...`. **Do not** set this to `http://localhost:3000` (that is the frontend port). |
| `NEXT_PUBLIC_DEMO_MODE`              | `false`                                       | When `true`, the UI shows a persistent "demo restaurant" banner. The backend also exposes `POST /api/demo/seed` (see `backend/core/__init__.py`).     |
| `RESTAURANT_DB_PATH`                 | `restaurant.db`                               | Backend SQLite file path.                                                                                                                             |
| `RESTAURANT_TAX_RATE`                | `0.0`                                         | Default tax rate (fraction, e.g. `0.05` for 5%). Applied server-side.                                                                                 |
| `RESTAURANT_REQUIRE_IDEMPOTENCY_KEY` | `true`                                        | If true, `POST /api/orders` requires an `Idempotency-Key` header.                                                                                     |
| `CORS_ALLOW_ORIGINS`                 | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated list of allowed origins.                                                                                                              |

---

## Available commands

### `make` shortcuts (preferred)

Run `make help` to see every target. The most useful ones:

| Command         | What it does                                                   |
| --------------- | -------------------------------------------------------------- |
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
| `make ci`       | Run every quality gate (typecheck, lint, format, tests, e2e).  |
| `make clean`    | Remove build artifacts, caches, dev DB.                        |

### `npm` (frontend)

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

### `python` (backend)

| Command                                | Purpose                                                            |
| -------------------------------------- | ------------------------------------------------------------------ |
| `python run.py`                        | Start the API (uvicorn with hot reload).                           |
| `python run.py --no-reload`            | Start the API as a single process. Use this for CI / tests.        |
| `python worker.py`                     | Start the background worker (heartbeat only in Phase 3).           |
| `python worker.py --once`              | Run a single tick and exit (smoke test).                           |
| `pytest -q`                            | Run the test suite.                                                |
| `ruff check .` / `ruff format .`       | Lint / format the backend (optional dep).                          |
| `pip install -r requirements.txt`      | Runtime deps.                                                      |
| `pip install -r requirements-ml.txt`   | Add Prophet + pandas + numpy (heavy; only needed for predictions). |
| `pip install -r requirements-dev.txt`  | Add pytest + httpx for local testing.                              |
| `pip install -r requirements-lint.txt` | Add ruff for local linting.                                        |

---

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system design, layering,
  why each piece is where it is, why each piece is not where it isn't.
- [`docs/API.md`](docs/API.md) — endpoint reference with example
  requests/responses (the source of truth is the FastAPI auto-generated
  OpenAPI schema at http://localhost:8000/docs once the backend is running).
- [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) — development workflow,
  how to add a feature, how to add a test, debugging tips.
- [`docs/PHASES.md`](docs/PHASES.md) — the rebuild history: what was
  wrong, what was fixed, and the validation evidence for each phase.
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — common errors
  and how to fix them.

---

## Project status

Phases 0–3 of the rebuild are **complete and validated**.

| Phase | Scope                                                                                    | Status |
| ----- | ---------------------------------------------------------------------------------------- | ------ |
| 0     | Make the system truthful (server-driven, no fake data, proper health checks)             | ✓      |
| 1     | Real operational loop (order lifecycle, kitchen tickets, inventory ledger, RBAC)         | ✓      |
| 2     | Trustworthy forecasting (baselines, backtester, model provenance)                        | ✓      |
| 3     | Commercial readiness scaffolding (suppliers, POs, payments, offline POS, audit, metrics) | ✓      |

Every audit gate from the original brief is green. See
[`docs/PHASES.md`](docs/PHASES.md) for the full evidence trail, and
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the design rationale.

### Intentionally not built (deferred to Phase 4+)

- Multi-tenant `restaurant_id` on every operational table
- Real payment-provider webhooks (Razorpay / Stripe)
- Discount codes + order modifiers
- Service worker + IndexedDB outbox (localStorage fallback works today)
- Alembic for proper migrations (in-place `_ensure_column` is Phase 0–3)
- PostgreSQL + `pg_dump` cron
- Tables / floor plans for sit-down restaurants
- Generated TypeScript client from FastAPI's OpenAPI schema
- Structured JSON logging + Sentry integration

---

## License

UNLICENSED — private project. Not for redistribution.
