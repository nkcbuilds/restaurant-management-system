# Architecture

This document explains **why** RestaurantOS is shaped the way it is: what
each layer does, what each layer deliberately does NOT do, and which
trade-offs you'd revisit before scaling.

If you only have 5 minutes, read the **One-page map** below. The rest of
the document expands each box.

---

## One-page map

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Next.js (port 3000)                           │
│                                                                      │
│  app/                components/        lib/         hooks/          │
│  ─────               ──────────         ────        ──────          │
│  RSC + client        shadcn/ui          http.ts      (reserved)      │
│  pages              primitives          store.ts                     │
│  (page.tsx)                            env.ts                        │
│                                         types.ts                      │
│  client/                              queries/                       │
│  ───────                              ────────                       │
│  api/sync         TanStack Query ────────► FastAPI                    │
│  api/sync/health  hooks (per resource)                              │
│                                                                      │
│            ┌──────────────────────────────────────────┐             │
│            │  Zustand (transient UI only)             │             │
│            │  • cart                                  │             │
│            │  • open dialogs                          │             │
│            │  • active filters                        │             │
│            │  NEVER server data                      │             │
│            └──────────────────────────────────────────┘             │
│                                                                      │
│            ┌──────────────────────────────────────────┐             │
│            │  offline.ts (outbox)                     │             │
│            │  • POST /api/orders/replay-batch        │             │
│            │  • auto-flush on `online` event          │             │
│            └──────────────────────────────────────────┘             │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  │  fetch + Idempotency-Key
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         FastAPI (port 8000)                          │
│                                                                      │
│  main.py                 models.py          database.py              │
│  ────────                ─────────          ───────────              │
│  routes /               Pydantic           SQLite (dev)              │
│  deps /                  request/response   PostgreSQL (prod)        │
│  error handlers          schemas                                     │
│                                                                      │
│  core/                   services/            jobs/                   │
│  ─────                   ────────            ─────                   │
│  config (env)            prediction_engine   (worker.py)              │
│  errors.py               (baselines +                               │
│  (HTTPException          Prophet lazy                                │
│   preservation)          import)                                    │
│                                                                      │
│  ml_predictions.py       baselines.py         backtest.py             │
│  ────────────────       ───────────         ──────────              │
│  structured             same-weekday         walk-forward             │
│  predictions            moving-avg           backtester               │
│  with model             recent-wtd                                  │
│  provenance             (3 baselines)        backtest_cli.py          │
│                                                  (CLI tool)          │
└──────────────────────────────────────────────────────────────────────┘
                                  ▲
                                  │
              ┌───────────────────┴───────────────────┐
              │                                       │
              ▼                                       ▼
       ┌──────────────┐                        ┌──────────────┐
       │  worker.py   │                        │  webhooks /  │
       │  (separate   │                        │  payment     │
       │  process)    │                        │  providers   │
       └──────────────┘                        └──────────────┘
       (Phase 4+)                              (Phase 4+)
```

---

## The core principle: one source of truth

Every screen reads from the same backend over HTTP. There is exactly
one place where an order becomes "real": the database row in
`backend/database.py`. There is exactly one place where a forecast is
computed: `backend/ml_predictions.py`. The browser never holds a copy
of business state.

This means:

- **Refresh pulls fresh state.** Two devices see the same data within
  one polling cycle (10s for kitchen; on-demand for everything else).
- **Killing the backend never lies.** `app/api/sync/health` returns 503
  when the FastAPI process is down. The dashboard badge shows "Offline",
  not "Live".
- **The frontend can't disagree with itself.** There is no client-side
  mirror of order data; the cart is the only transient client state.

The one exception is the **offline outbox** (`lib/offline.ts`): when
the browser can't reach the backend, orders are queued locally and
replayed through `POST /api/orders/replay-batch` when connectivity
returns. Each captured order carries an idempotency key so the replay
is safe to retry. **The outbox is not a database; it's a write-ahead
log for connectivity failures only.** When the network is healthy, it
is empty.

---

## Frontend layers

### Pages (`app/`)

Each page is a React Server Component by default and gets a client
component for anything that needs state. Pages do not call `fetch`
directly; they consume TanStack Query hooks from `lib/queries/`.

| Page        | Route          | Data source                                                                    |
| ----------- | -------------- | ------------------------------------------------------------------------------ |
| Dashboard   | `/`            | `useOrders`, `useIngredients`, `useSystemHealth`                               |
| Inventory   | `/inventory`   | `useIngredients`, `useDishes`, mutations for create/update                     |
| Orders      | `/orders`      | `useDishes`, `useIngredients`, `useOrders`, `usePlaceOrder`, `useOfflineQueue` |
| Kitchen     | `/kitchen`     | `useKitchenTickets` (auto-refresh 10s), `useTransitionOrder`                   |
| Predictions | `/predictions` | `usePredictions`, `usePrepPlan`, `usePurchaseRecommendations`, `useBacktest`   |

### API proxy (`app/api/sync/`)

The Next.js layer proxies two health endpoints that don't go through
TanStack Query:

- `POST /api/sync` — proxied to FastAPI's `/api/sync`. Returns 503
  when the backend is unreachable.
- `GET /api/sync/health` — proxied to `/api/health`. Used by the
  dashboard's sync-status badge.

These exist so the dashboard can render an honest "Online/Offline"
indicator without depending on the FastAPI process being reachable from
the user's browser. (CORS, firewalls, dev tunnels, etc.)

### State: three things, three jobs

| Tool               | What it holds                                                         | Lifetime                  |
| ------------------ | --------------------------------------------------------------------- | ------------------------- |
| **TanStack Query** | All server data. Cached, refetched, deduped, invalidated on mutation. | Process + cache TTL       |
| **Zustand**        | Cart, dialogs, filters. NEVER server data.                            | Process                   |
| **localStorage**   | Offline outbox only. (`lib/offline.ts`)                               | Persistent across reloads |

The Zustand store is one file: `lib/store.ts`. Adding a new piece of
client UI state goes there; adding a new piece of server data goes into
a query in `lib/queries/`.

### TypeScript boundary

The frontend types in `lib/types.ts` are hand-written mirrors of the
FastAPI Pydantic models. They are not generated. For a project of this
size, the duplication cost is low; the alternative (OpenAPI codegen) is
worth it when the schema changes more than once a week. See
[`docs/CONTRIBUTING.md`](CONTRIBUTING.md) for the "when to add a field"
checklist.

---

## Backend layers

### Routes (`backend/main.py`)

All HTTP routes live in one file for now. Phase 4 will split this
into `backend/api/` modules per resource. Until then, the file is
~600 lines but each section is clearly delineated by `# ----` headers
and grouped by resource (dishes, ingredients, orders, kitchen, …).

Every route uses `ApiResponse[T]` from `backend/models.py` as the
envelope:

```json
{ "success": true,  "data": <T> }
{ "success": false, "error": { "detail": ..., "error_id": "..." } }
```

Routes that mutate state validate RBAC via `_require_role()` reading
`X-User-Role`. The header is documented as **dev-only auth**; a real
auth layer (sessions, JWT, OAuth) is Phase 4.

### Error handling (`backend/core/errors.py`)

A single global handler installed via `install_error_handlers(app)`:

- `HTTPException` is preserved (404 stays 404, 409 stays 409, 403 stays
  403). The detail message is returned verbatim.
- Anything else returns 500 with `error_id` (a short random hex
  string) and a generic message. The full traceback is logged with the
  same `error_id` so support can correlate user reports to logs.

The handler is installed in `main.py` BEFORE any route is registered,
so it catches errors from every endpoint.

### Database (`backend/database.py`)

A thin SQLite/PostgreSQL wrapper. Connection-per-request via
`get_connection()`. Every mutating method opens a transaction and
rolls back on failure.

Why one file: SQLAlchemy / SQLModel would add a layer of indirection
without changing the queries. When the project outgrows this — when
we need connection pooling, row-level locking, or migration tooling
(Alembic) — we'll migrate. Until then, raw SQL is readable.

### Inventory ledger (within `database.py`)

The `inventory_transactions` table is the audit log of every stock
change. Every change writes a row with a signed `quantity_change` and a
`transaction_type` from:

- `usage` / `consumption` — order fulfillment
- `adjustment` — manual edit (records the DELTA, see below)
- `waste` — spoilage / staff meal / prep error
- `physical_count` — daily stock take (records the variance)
- `purchase` — PO receipt (weighted-average cost update)

**Critical invariant:** `quantity_change` is always the **signed
delta**, never the absolute value. The original code wrote the
absolute value, which corrupted the variance report. Tests in
`tests/test_inventory_ledger.py` pin this contract.

### Predictions (`backend/ml_predictions.py` + `backend/baselines.py`)

Two layers, separated by intent:

- **`backend/baselines.py`** — three simple, deterministic
  predictors. `baseline_same_weekday`, `baseline_moving_average`,
  `baseline_recent_weighted`. Each returns a `BaselineForecast`
  dataclass with `point`, `low`, `high`, `confidence`, `data_sufficiency`,
  `model`. These never raise.
- **`backend/ml_predictions.py`** — orchestrates the baselines, picks
  the best one per `(dish, period)`, optionally layers Prophet on top
  (when installed), formats the result for the API. The Prophet import
  is lazy: the API boots without it.

The prediction output carries **model provenance**: which model
produced it, what confidence level, how much data was available, and
a human-readable `reason` string. The UI renders this verbatim. This
is the answer to "why did the kitchen prepare 47 portions of pasta
tonight?" — it says so on screen.

### Backtester (`backend/backtest.py` + `backend/backtest_cli.py`)

A walk-forward backtester that simulates "what would each model have
predicted on date D, given only data available before D". Reports
MAE, WAPE, bias, stockout rate, and over-prep waste per (dish, period)
per model. The CLI (`python backtest_cli.py --days 90`) prints a
table; the API (`GET /api/predictions/backtest`) returns JSON.

This is what gives the prediction numbers **trust**. Instead of a
hardcoded "85% accuracy", the operator sees "on the last 90 days, the
same-weekday baseline had WAPE 0.011 on Pasta / evening, which is why
that's what the engine picks for that slot."

---

## Worker process (`backend/worker.py`)

A separate Python process. **The API process does no scheduling.**
This is deliberate: under multi-worker Gunicorn / uvicorn
deployments, an in-process scheduler would duplicate. The worker
owns:

- Forecast generation on a schedule (Phase 4: real jobs)
- Daily summary rollups
- Reorder recommendations (Phase 4)
- Notification fan-out (Phase 4)

In Phase 3 the worker is a heartbeat loop that exits 0 on
`--once`. The wiring is in place; the jobs land in Phase 4.

Run with `python worker.py` (foreground) or `make worker` (Makefile
wrapper). In production, run it as a separate systemd / Docker /
Kubernetes service.

---

## Data flow examples

### Happy path: cashier takes an order

```
Browser /orders
  └─ usePlaceOrder.mutate(items)
       └─ POST /api/orders  (Idempotency-Key: <uuid>)
            └─ FastAPI route create_order
                 ├─ db.create_order(...)
                 │    ├─ Look up dish prices from DB (ignore client values)
                 │    ├─ Compute subtotal, tax, total server-side
                 │    ├─ _check_inventory_for_items(cursor, ...)   ← stock check
                 │    ├─ INSERT INTO orders          ← single source of truth
                 │    ├─ INSERT INTO kitchen_tickets (auto-created)
                 │    ├─ INSERT INTO order_items
                 │    └─ _update_inventory_for_dish  ← ledger write
                 │
                 └─ Return 201 with the persisted order
       └─ TanStack Query invalidates ['orders'], ['ingredients'], ['dishes']
       └─ Browser re-fetches → stock reflects the change
```

### Sad path: backend is down

```
Browser /orders
  └─ usePlaceOrder.mutate(items)
       └─ POST /api/orders  → fetch fails (TypeError: Failed to fetch)
       └─ usePlaceOrder.mutate's onError fires
       └─ Orders page catches the error → offline.queue(...)
            └─ enqueueOfflineOrder → localStorage['restaurantos:offline_outbox']
       └─ Orders page banner shows "1 order waiting to sync"
       └─ When browser fires `online` event:
            └─ useOfflineQueue.flush() → POST /api/orders/replay-batch
                 └─ Server dedupes by idempotency_key
                 └─ Returns {accepted, duplicates, failed}
       └─ Banner clears
```

### Forecast request

```
Browser /predictions
  └─ usePredictions(date)
       └─ GET /api/predictions?date=2026-07-15
            └─ engine.get_structured_predictions(date)
                 └─ For each (dish, period) with history:
                      ├─ run_all_baselines(history, date, period)
                      │    ├─ baseline_same_weekday
                      │    ├─ baseline_moving_average
                      │    └─ baseline_recent_weighted
                      ├─ pick_best(baselines)  ← highest confidence non-insufficient
                      └─ _format_prediction(...)  ← adds model_used, reason
            └─ Return [{dish_id, predicted_demand, low, high, ...}, ...]
       └─ TanStack Query caches by date
       └─ Predictions page renders model name, range, reason
```

---

## Quality gates

| Layer         | Tool               | Config                                          | Where                          |
| ------------- | ------------------ | ----------------------------------------------- | ------------------------------ |
| Frontend TS   | `tsc --noEmit`     | strict + `noUncheckedIndexedAccess`             | `tsconfig.json`                |
| Frontend lint | `next lint`        | `next/core-web-vitals` + `next/typescript`      | `.eslintrc.json`               |
| Frontend fmt  | Prettier           | 2-space, double quotes, semicolons off          | `.prettierrc.json`             |
| Backend lint  | Ruff               | E, W, F, I, B, UP                               | `ruff.toml`                    |
| Backend fmt   | `ruff format`      | double quotes, 4-space indent                   | `ruff.toml`                    |
| Backend types | mypy / Pydantic    | implicit via Pydantic v2                        | runtime                        |
| Tests         | pytest, vitest     | —                                               | `backend/tests/`, `__tests__/` |
| E2E           | Node script + curl | `scripts/e2e-smoke.cjs`, `scripts/e2e.{sh,ps1}` | `scripts/`                     |
| CI            | GitHub Actions     | Node 20, Python 3.10/3.11/3.12 matrix           | `.github/workflows/ci.yml`     |

`make test` and `make e2e` run the same gates locally. The CI matrix
runs them in parallel on every PR.

---

## Trade-offs you'd revisit before scaling

These are choices that are correct for the current size and would
need rethinking at a different scale:

1. **Single `database.py` file.** Fine at 1700 lines and ~12
   resources. Migrate to SQLAlchemy/SQLModel + Alembic when you
   add a second engineer.
2. **All routes in one `main.py` file.** Fine at ~600 lines. Split
   into `backend/api/{dishes,ingredients,orders,...}.py` when this
   file exceeds 1000 lines.
3. **Hand-written TS types in `lib/types.ts`.** Fine at ~120 lines.
   Switch to OpenAPI codegen (`openapi-typescript`) when the schema
   changes more than once a week.
4. **`X-User-Role` header for auth.** **Dev-only.** Replace with
   sessions / JWT before any deployment with real customers.
5. **SQLite for everything in dev.** Switch to PostgreSQL when
   you need concurrent writes from multiple workers, or when the
   DB exceeds a few GB.
6. **No service worker / IndexedDB.** The localStorage outbox
   works for a single browser tab and a few minutes of outage.
   Service worker + IndexedDB is needed for "the cashier's tablet
   was offline all evening" scenarios.
7. **3 baselines only.** Sufficient for the data volume we have.
   Add Prophet (or another model) when backtest WAPE stops improving
   as history grows.
