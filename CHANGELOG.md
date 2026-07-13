# Changelog

All notable changes to RestaurantOS are recorded here. Dates are in
`YYYY-MM-DD` format. Versions follow [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Fixed

- **`POST /api/orders` with empty `items` array.** Previously this
  returned 201 and created a $0 order with no line items. Now returns 400. The new test `test_empty_order_rejected` pins the contract.

## [Unreleased (docs)]

### Added — Documentation overhaul

- **`README.md` rewritten.** Reflects the current state of the project
  (Phases 0–3 complete) rather than the original "Phase 0 of a four-
  phase rebuild" framing. Adds an at-a-glance summary, a per-page
  description, a command reference, and a project-status table.
- **`docs/ARCHITECTURE.md` (new).** The system design: why each piece
  is where it is, why each piece is deliberately not where it isn't.
  Includes a one-page map, layer-by-layer walkthrough, three worked
  data-flow examples (order happy path, offline replay, forecast
  request), and the trade-offs you'd revisit before scaling.
- **`docs/API.md` (new).** Textual reference for every REST endpoint:
  method, path, headers, RBAC, response shape, status codes. Three
  example flows. Note: the FastAPI auto-generated OpenAPI schema at
  `http://localhost:8000/docs` is the source of truth — this is the
  quick map.
- **`docs/CONTRIBUTING.md` (new).** Practical guide for new
  contributors: setup, day-to-day loop, "where code goes" decision
  tree, testing strategy, debugging tips, code style, and three
  checklists (adding a field, adding a page, reviewing a PR).
- **`docs/TROUBLESHOOTING.md` (new).** Common errors and how to fix
  them, organised by symptom (setup / dev / testing / production).
  Includes the standard debugging procedure and a "getting help"
  escalation.
- **`docs/PHASES.md` (moved + rewritten).** The previous
  `PHASES.md` lived at the workspace root and described the rebuild
  as a plan. It's been moved into the repo and rewritten as the
  rebuild history: what was wrong, what was fixed, and the evidence
  trail for each phase.
- **`CHANGELOG.md` (this file).** A canonical, append-only history of
  every notable change.

### Added — Tooling (closed Definition-of-Done #7)

- **`Makefile`** with `setup`, `test`, `e2e`, `dev`, `build`, `lint`,
  `format`, `clean`, `ci`, `worker`, `stop`, and `help` targets.
- **`scripts/bootstrap.ps1`** — Windows equivalent of `make setup`.
- **`scripts/test.ps1`** — Windows equivalent of `make test`.
- **`scripts/e2e.sh`** / **`scripts/e2e.ps1`** — boot the backend,
  run the 9-step smoke, tear it down. The PowerShell version probes
  `127.0.0.1` to avoid PowerShell's IPv6-vs-uvicorn IPv4 timeout.
- **`backend/run.py --no-reload`** — single-process mode (recommended
  for `make e2e` and any other scripted invocation that touches the
  DB file). Dev mode (no flag) keeps hot reload.

---

## [0.2.0] — Phases 0–3 complete

### Phase 0 — Make the system truthful

- Backend is the single source of truth for dishes, ingredients, and
  orders. Frontend uses TanStack Query; no `localStorage`-as-DB.
- Server-side price, tax, and total calculation; client values
  ignored.
- `Idempotency-Key` on order creation; duplicates return 200 with the
  original order (not 201).
- `/api/health` actually probes the database; returns 503 on outage.
- `app/api/sync` returns 503 when the backend is unreachable.
- `update_ingredient_quantity` records the **delta** in the ledger,
  not the absolute value.
- Backend error handling preserves HTTP status codes (no more
  404 → 500).
- `next.config.mjs` has `ignoreBuildErrors` / `ignoreDuringBuilds`
  removed.
- DEMO_MODE banner and stub `POST /api/demo/seed` endpoint.

### Phase 1 — Real operational loop

- Full 8-state order lifecycle with server-enforced transitions.
- Cancellation reverses inventory consumption per `reverse_on_cancel`
  policy (`always` / `preparing_only` / `never`).
- Kitchen tickets: one row per order; status mirrors the order.
- `POST /api/inventory/waste`, `POST /api/inventory/count`,
  `GET /api/inventory/variance`.
- RBAC via `X-User-Role`: `cashier < kitchen < inventory < manager <
owner`.
- Kitchen page auto-refreshes every 10 seconds.

### Phase 2 — Trustworthy forecasting

- Three named baselines: `same_weekday`, `moving_average`,
  `recent_weighted`.
- Walk-forward backtester with MAE / WAPE / bias / stockout-rate /
  waste per `(dish, period)`.
- Predictions carry `model_used`, `model_confidence`,
  `data_sufficiency`, low/high range, and a human-readable `reason`.
- `GET /api/prep-plan`, `GET /api/purchase-recommendations`.
- Synthetic Monday-pattern validation: `baseline_same_weekday` wins
  with WAPE 0.011 vs 0.069/0.079.

### Phase 3 — Commercial readiness scaffolding

- Suppliers + Purchase Orders (weighted-average cost on receive).
- Payments with idempotency and split-tender support.
- Offline POS outbox with auto-flush on the browser `online` event.
- Audit log + minimal Prometheus `/metrics` endpoint.

### Tests

- **84** backend tests (pytest).
- **25** frontend tests (vitest).
- **9**-step end-to-end smoke (Node).

### CI

- ~~GitHub Actions matrix (Node 20, Python 3.10 / 3.11 / 3.12).~~ —
  _CI was removed in a later pass._
- ~~`make ci` mirrors the CI gates locally.~~ — _CI was removed in a
  later pass. `make ci` is still available; the Makefile is the
  source of truth._

---

## Earlier history

See `git log --oneline`. The four "Phase N" commits are:

- `5709bda` Phase 0 cleanup
- `ba98747` Phase 1: real operational loop
- `ca2d5c3` Phase 2: trustworthy forecasting
- `9f691f6` Phase 3: commercial readiness scaffolding
- `0c14710` Add Makefile + e2e scripts (closes Definition-of-Done #7)
