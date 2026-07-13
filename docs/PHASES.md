# RestaurantOS — Rebuild History

> **Status:** All four phases complete and validated. This document
> records what was wrong, what was fixed, and the evidence trail. For
> the current state of the project, see [`README.md`](../README.md) and
> [`ARCHITECTURE.md`](ARCHITECTURE.md).

This is the rebuild history. It is kept in the repo as a reference for
future contributors who wonder "why is this file here?" or "why is
this structured this way?"

---

## Why the rebuild happened

A fresh audit of the previous build surfaced 11 problems, ranging
from "the dashboard is lying to the operator" to "the backend runs
on the operator's machine". The previous code worked in a demo, but
no operator could trust the numbers, no two devices would see the
same data, and the process would have collapsed under any real load.

The rebuild was planned in four phases, each with a clear scope and
a validation gate. Each phase committed independently so a partial
failure would not block shipping.

---

## Audit findings (the 11 problems)

| #   | Problem                                                                                                     | Severity |
| --- | ----------------------------------------------------------------------------------------------------------- | -------- |
| 1   | "No single source of truth" — Inventory/Orders used localStorage as a parallel database                     | Critical |
| 2   | "Sample and real data are mixed" — Dashboard showed hardcoded revenue graphs                                | Critical |
| 3   | "AI forecasting not using Prophet" — frontend used `Math.random() * avg`                                    | High     |
| 4   | "Order pricing/inventory validation not secure" — server trusted client-supplied prices                     | High     |
| 5   | "Inventory accounting too simplistic" — one mutable `quantity_today`                                        | High     |
| 6   | "Sync failures disguised as success" — `/api/sync` returned 200 even when the backend was down              | High     |
| 7   | "Background jobs running in web server" — Prophet scheduler in lifespan, would duplicate under multi-worker | Medium   |
| 8   | "Backend error handling converts valid errors into 500s" — try/except caught HTTPException 404s             | High     |
| 9   | "Production quality gates are switched off" — `ignoreBuildErrors`, `ignoreDuringBuilds`                     | High     |
| 10  | "Repo contains Python virtual environment" — 11,800 paths in `git status`                                   | High     |
| 11  | "Documentation contradicts the actual project" — wrong port, conflicting setup steps                        | High     |

---

## Phase 0 — Make the system truthful

**Scope:** Stop the lying. No sample data, no fake sync success, no
`ignoreBuildErrors`. Get one real end-to-end flow working: dish CRUD

- ingredient CRUD + order creation, all from the browser, all hitting
  the backend.

**Key changes:**

- `lib/queries/*.ts` use TanStack Query against the FastAPI backend;
  no `localStorage` reads/writes for server data
- `/api/health` actually probes the DB; returns 503 when down
- `POST /api/orders` returns 200 (replay) or 201 (create) based on
  `Idempotency-Key`
- `/api/predictions` never 503s without Prophet (baselines always run)
- Backend error handler preserves `HTTPException`; logs unexpected
  with traceback + `error_id`
- ~~GitHub Actions CI runs every gate~~ — _CI was added in a later
  commit and removed in the docs-overhaul pass. The Makefile is the
  source of truth._
- Ruff config + `requirements-lint.txt`
- `.gitignore` excludes `venv/`, `__pycache__/`, `*.db`, etc.
- 11,800 venv paths untracked from git index

**Validation (Phase 0.D gate):** all green. 19 backend + 18 frontend
tests. `git status` shows ≤ 5 untracked files outside `.next/`.
`pytest -q` green. `npm run build` green (no `ignoreBuildErrors`).
`curl /api/health` returns 200 when DB up, 503 when down. Over-stock
order returns 409. Idempotent replay returns 200 not 201. Idempotency
duplicate returns 201 the second time.

**Commit:** `5709bda`

---

## Phase 1 — Real operational loop

**Scope:** Server is the source of truth for orders, inventory, and
kitchen state. Browser is a thin client.

**Key changes:**

- Full 8-state order lifecycle with server-enforced transitions:
  `draft → submitted → accepted → preparing → ready → served →
completed` plus `cancelled`
- Cancellation reverses inventory consumption per
  `reverse_on_cancel` policy (`always` / `preparing_only` / `never`)
- Kitchen tickets: one row per order, status mirrors the order
- `POST /api/inventory/waste` records spoilage / staff meals
- `POST /api/inventory/count` records daily stock takes with variance
- `GET /api/inventory/variance?from&to` theoretical-vs-actual report
- RBAC via `X-User-Role` header: `cashier < kitchen < inventory <
manager < owner`
- Kitchen page auto-refreshes every 10s

**Validation:** All Phase 0 tests still green. Live e2e walk-through:
`submitted → accepted → preparing → ready → served → completed`,
illegal transition (cancel a completed) returns 409, cashier trying
to accept returns 403. 48 backend tests.

**Commit:** `ba98747`

---

## Phase 2 — Trustworthy forecasting

**Scope:** Forecasting becomes a trustworthy operational tool, not a
magic number on a dashboard.

**Key changes:**

- Three baselines in `backend/baselines.py`:
  `baseline_same_weekday`, `baseline_moving_average`,
  `baseline_recent_weighted`. Each returns `BaselineForecast(point,
low, high, confidence, data_sufficiency, model)`.
- `backend/backtest.py` walks history forward by `horizon_days`,
  evaluates every baseline per `(dish, period)`, reports MAE / WAPE /
  bias / stockout-rate / waste. Marks a per-key winner.
- `backend/backtest_cli.py`: `python backtest_cli.py --days 90` prints a
  per-model summary table.
- `PredictionEngine.get_structured_predictions` runs all three
  baselines, picks the highest-confidence non-insufficient one.
- Output carries `model_used`, `model_confidence`, `data_sufficiency`,
  low/high range, and a human-readable `reason`.
- `GET /api/prep-plan` returns per-(dish, period) prep with the
  ingredients needed.
- `GET /api/purchase-recommendations` returns per-ingredient
  shortage and cost estimate.
- Synthetic Monday-pattern validation: `baseline_same_weekday` wins
  with WAPE 0.011 vs 0.069/0.079.

**Validation:** All Phase 0–1 tests green. Synthetic dataset
validates that baselines beat random. 73 backend tests.

**Commit:** `ca2d5c3`

---

## Phase 3 — Commercial readiness scaffolding

**Scope:** Move from single-restaurant prototype to something a paying
customer could run.

**Key changes:**

- `suppliers`, `purchase_orders`, `purchase_order_items` tables
- Receiving a PO writes `purchase` ledger entries and updates
  `cost_per_unit` to a quantity-weighted average
- `payments` table with split-tender support (many payments per order)
- `POST /api/payments` with `Idempotency-Key` header
- `POST /api/orders/replay-batch` for offline replay that dedupes by
  idempotency_key
- Frontend `lib/offline.ts`: localStorage-backed outbox
- Frontend `lib/queries/offline.ts`: `useOfflineQueue` hook with
  auto-flush on the browser `online` event
- Orders page shows a "N orders waiting to sync" banner
- `audit_log` table captures every state-changing action
- `GET /api/audit` (owner-only) returns the most recent 100
- Minimal `GET /metrics` Prometheus-style exposition

**Validation:** All Phase 0–2 tests green. Live e2e (supplier → PO →
receive → order → payment → audit → metrics → offline replay →
idempotency dedup) produces the expected results. 85 backend + 25
frontend tests.

**Commit:** `9f691f6`

---

## Final validation (post-Phase 3)

```
[1/9] make help              -> help table renders
[2/9] make test              -> 25 frontend + 85 backend tests green
[3/9] make lint              -> ESLint + ruff clean
[4/9] make build             -> production build green
[5/9] make e2e x10           -> 10 consecutive PASS
[6/9] pytest -q              -> 85 passed
[7/9] ruff check             -> All checks passed!
[8/9] ruff format check      -> 29 files already formatted
[9/9] worker --once          -> exits 0
```

---

## Tooling follow-ups (post-Phase 3)

**Makefile + e2e scripts** (`0c14710`)

The original audit said:

> 7. `git clone && make && make test` reproduces a working system on
>    a fresh machine.

That criterion was deferred to "Phase 4". It is **now closed**:

- `Makefile` — `make setup`, `make test`, `make e2e`, `make dev`,
  `make build`, `make lint`, `make format`, `make clean`, `make ci`,
  `make worker`, `make stop`, `make help`
- `scripts/bootstrap.ps1` — Windows equivalent of `make setup`
- `scripts/test.ps1` — Windows equivalent of `make test`
- `scripts/e2e.sh` / `scripts/e2e.ps1` — boot the backend, run the
  smoke, tear it down. The PowerShell version probes `127.0.0.1` to
  avoid PowerShell's IPv6-vs-uvicorn IPv4 timeout.
- `backend/run.py --no-reload` — single-process mode (recommended
  for `make e2e` and any other scripted invocation that touches the
  DB file);
  uvicorn's auto-reloader cannot restart mid-request.

---

## Definition of done — status

| #   | Goal                                                                                     | Status |
| --- | ---------------------------------------------------------------------------------------- | ------ |
| 1   | Every number on every screen is either real, estimated, or labelled                      | ✓      |
| 2   | Two devices see the same data within 5 seconds of each other                             | ✓      |
| 3   | Killing the backend never makes the UI claim success                                     | ✓      |
| 4   | A new cashier can take an order without being told what prices are                       | ✓      |
| 5   | The manager can explain why the kitchen prepared 47 portions of pasta tonight            | ✓      |
| 6   | A power user can run the system offline for an evening and sync cleanly the next morning | ✓      |
| 7   | `git clone && make && make test` reproduces a working system on a fresh machine          | ✓      |

---

## Lessons

The four most expensive mistakes in the previous build were all
"things that look like they work but lie":

1. **`localStorage` as a database.** Looked fast; meant every browser
   tab was a different restaurant.
2. **`Math.random() * avg` for forecasting.** Looked intelligent;
   meant the kitchen prepared random portions.
3. **Hardcoded `200 OK` on sync failures.** Looked alive; meant the
   operator couldn't tell when the backend was down.
4. **`ignoreBuildErrors: true`.** Looked like progress; meant the
   production build succeeded with type errors.

The four cheapest fixes were all "make the system say what it's
actually doing":

1. **TanStack Query against the backend.** `localStorage` doesn't get
   re-implemented when the API changes.
2. **`is_valid_transition` map.** Illegal transitions return 409;
   legal ones succeed; the client can't lie.
3. **`_ensure_column` migrations and idempotency keys.** Every
   schema change and every retry is safe by construction.
4. **`make test && make e2e` on a fresh clone.** The repo doesn't ship
   a build that wouldn't run on a clean checkout. _(CI was tried and
   removed — see the "Tooling follow-ups" section for the rationale.)_

The order mattered: every Phase N+1 fix relied on Phase N's
foundation. Trying to add offline-mode on top of `Math.random()`
would not have worked.
