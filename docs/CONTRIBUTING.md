# Contributing

A practical guide to working on RestaurantOS. If you only have 5
minutes, read **Setup**, **Day-to-day loop**, and the **Checklists** at
the bottom. The rest of the document fills in the why.

---

## Setup

```bash
git clone <repo>
cd restaurant-management-system
make setup        # installs frontend + backend deps (creates backend/.venv)
make test         # confirm everything is green before you start
```

Windows PowerShell users:

```powershell
git clone <repo>
cd restaurant-management-system
.\scripts\bootstrap.ps1
.\scripts\test.ps1
```

Read [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) once before you start
hacking. It explains why the code is shaped the way it is, which saves
you from arguing with the wrong invariants.

---

## Day-to-day loop

1. **Make sure `make test` is green.** If it isn't on `main`, fix that
   before starting your change. The Makefile is the source of truth
   for what "green" means.

2. **Pick a small, well-scoped change.** Phrases like "let me also
   refactor…" usually end up blocking PRs for a week. Finish one
   thing, open the PR, ship it.

3. **For data-shape changes, update the contract first.** See the
   [Adding a field](#adding-a-field-to-an-api-resource) section below.

4. **Write the test before the code.** A failing test that describes
   the desired behaviour, then the code that makes it pass. The
   backend has 84 tests; the frontend has 25. The CI gate won't
   merge without them.

5. **Run `make lint && make test && make e2e` locally before pushing.**
   `make e2e` boots the backend, runs the 9-step smoke, tears down.
   10 consecutive passes confirms stability.

6. **One commit per logical change.** If you can't write a one-line
   summary of what a commit does, it should probably be two commits.

---

## Where code goes

### Adding a feature

Ask in this order:

1. **Is this server state or client UI state?**

   - Server state → new query in `lib/queries/<resource>.ts`, new
     endpoint in `backend/main.py`, new method in
     `backend/database.py`.
   - Client UI state → new selector in `lib/store.ts`, or local
     `useState` if it's truly local to one component.

2. **Does this touch an existing resource?**

   - Yes → extend the existing `lib/queries/<resource>.ts`,
     `backend/main.py` route group, and `backend/database.py` methods.
     Don't create a parallel file.
   - No → use the existing patterns as a template. Look at
     `lib/queries/orders.ts` and the corresponding `/api/orders*`
     routes.

3. **Does it need a kitchen / inventory role gate?** Almost
   everything that mutates does. Add `_require_role(x_user_role, "...")`
   to the route and a header to the test request.

### Adding a field to an API resource

This is the most common drift source. Update **four** places in
lockstep:

1. **Backend Pydantic model** in `backend/models.py`.
2. **Backend DB** in `backend/database.py` — add the column to the
   `CREATE TABLE` and, if it can be missing on existing rows, add
   an `_ensure_column` migration. (Phase 4: switch to Alembic.)
3. **Backend route** — include the new field in the response shape
   from `database.py`'s getter methods.
4. **Frontend type** in `lib/types.ts`. Add the field as
   `<field_name>: <type>` and grep for usages — TypeScript strict
   will flag every place that constructs the type without it.

If the field is computed (e.g., `available_stock = quantity_today -
reserved`), don't store it — compute it in the route or in a query
helper. Storing computed fields is how databases end up lying.

### Adding a frontend page

1. Create `app/<route>/page.tsx`. Server Component by default.
2. Mark `"use client"` at the top if you need state, effects, or
   browser APIs.
3. Use TanStack Query hooks from `lib/queries/`. Don't fetch
   directly in the page.
4. Add the route to `components/sidebar.tsx` navigation. If the page
   has a live count that should appear as a sidebar badge (e.g., open
   kitchen tickets), wire it to a `useKitchenTickets()`-style hook.
5. If the page is the home for a new resource, add it to
   `lib/queries/index.ts` exports.

### Adding a backend endpoint

1. The route lives in `backend/main.py` (Phase 4: split into
   `backend/api/<resource>.py`).
2. Use the standard envelope: `ApiResponse[T]` for normal returns,
   `JSONResponse` when you need a specific status code.
3. Use the right HTTP status — `201` for create, `200` for success,
   `400` for validation, `403` for RBAC, `404` for missing, `409` for
   conflict, `500` for server error with `error_id`.
4. For state mutations, call `_require_role(x_user_role, "minimum")`.
5. For idempotency, read the `Idempotency-Key` header (see
   `POST /api/orders` for the canonical pattern).
6. Add a pytest in `backend/tests/test_phaseN_*.py`.

---

## Testing

### Backend tests (`backend/tests/`)

Use the `db` fixture from `conftest.py`. It creates a fresh
on-disk SQLite in `tmp_path` for every test:

```python
def test_something(db):
    ing = db.create_ingredient({"name": "Flour", ...})
    assert db.get_ingredient_by_id(ing)["name"] == "Flour"
```

For endpoint-level tests use `TestClient`:

```python
def test_endpoint(temp_db_path):
    from database import DatabaseManager
    import main
    DatabaseManager(temp_db_path)
    main.db_manager = DatabaseManager(temp_db_path)
    main.prediction_engine = PredictionEngine(main.db_manager)
    client = TestClient(main.app)
    r = client.get("/api/health")
    assert r.status_code == 200
```

Group related tests into one file per phase / per area:
`test_order_calc.py`, `test_order_lifecycle.py`, `test_inventory_ledger.py`,
`test_phase1_api.py`, etc.

### Frontend tests (`__tests__/`)

Vitest with jsdom. Pure logic tests are cheap to write and catch real
bugs:

```typescript
it("cart dedupes by dish_id", () => {
  const store = useUIStore.getState()
  store.addToCart("d1", 1)
  store.addToCart("d1", 2)
  expect(useUIStore.getState().cart).toEqual([{ dish_id: "d1", quantity: 3 }])
})
```

For TanStack Query hooks, mock `fetch` and assert the right URL was
called. For offline outbox, see `__tests__/offline.test.ts` — it
covers the queue, replay, dedup, and network-failure paths.

### E2E tests (`scripts/`)

The `scripts/e2e-smoke.cjs` script is the contract. It boots the backend
yourself with `--no-reload` (so the auto-reloader can't restart mid-
test), runs 9 assertions covering the happy path, idempotency, and
stock-overflow rejection.

If you change a behaviour that the smoke covers, update the smoke in
the same PR. The smoke is the only thing that proves the whole stack
works end-to-end.

---

## Debugging

### The frontend shows "Offline"

The dashboard reads `/api/sync/health`. Check, in order:

1. Is the FastAPI process running? `tasklist | grep python.exe` or
   `ps aux | grep uvicorn`.
2. Is port 8000 bound? `netstat -ano | findstr :8000` (Windows) or
   `lsof -i :8000` (POSIX).
3. Does `curl http://localhost:8000/api/health` return 200?
4. If yes but the UI still says Offline, the Next.js proxy
   `app/api/sync/health` is the broken link — check
   `NEXT_PUBLIC_API_URL`.

### A test passes locally but fails in CI

The most common cause: the test relied on a shared resource (a file
in `backend/`, a process on a port, the working directory). All tests
in `backend/tests/` should use the `db` or `temp_db_path` fixture
which guarantees isolation. If yours doesn't, fix it.

### A backend endpoint returns 500 with `error_id`

Find the `error_id` in `backend/restaurant_api.log`:

```bash
grep "<error_id>" backend/restaurant_api.log
```

The full traceback is on the same line. If the error is `no such
table: X`, the DB schema is out of sync — run `rm backend/restaurant.db`
to reset (only in dev).

### The uvicorn auto-reloader is restarting mid-request

If you see intermittent "no such table" errors when the backend has
been running a while, the auto-reloader might be detecting a change.
Run with `--no-reload`:

```bash
python backend/run.py --no-reload
```

The dev mode (no flag) is for interactive use. Tests, CI, and e2e
always pass `--no-reload`.

---

## Code style

### Python (enforced by Ruff)

- 100-column lines (Ruff default)
- Double quotes
- 4-space indent
- `from __future__ import annotations` at the top of every module
- Type hints on every public function
- Docstring on every module and every non-trivial function (one line
  is fine; aim for "the docstring is the API contract")

### TypeScript (enforced by ESLint + Prettier + tsc)

- Strict mode enabled (`tsconfig.json`)
- No `any` types. If you need to escape, use `unknown` and narrow.
- No `@ts-ignore`. If you must, comment why.
- Tailwind classes for styling; no inline `style={}` except for
  truly dynamic values.
- React Server Components by default; `"use client"` only when needed.
- Server state via TanStack Query, not `useEffect + fetch`.
- Client state via Zustand for cross-component; `useState` for
  local-only.

### Imports

- One module per import group, separated by blank line:

  ```typescript
  import { useQuery } from "@tanstack/react-query"

  import { Card } from "@/components/ui/card"

  import { useOrders } from "@/lib/queries/orders"
  ```

- No barrel imports from `index.ts` deep in the tree — they're slow
  and obscure the dependency graph. Only `lib/queries/index.ts` is
  meant to be imported widely.

---

## Checklists

### Adding a new endpoint

- [ ] Route in `backend/main.py` with the right status code
- [ ] RBAC gate if it mutates state
- [ ] Idempotency if it's a POST
- [ ] Returns `ApiResponse[T]` (or `JSONResponse` if custom status)
- [ ] Pydantic model in `backend/models.py`
- [ ] DB method in `backend/database.py` (with a small migration if
      the schema changed)
- [ ] TS type in `lib/types.ts`
- [ ] Query hook in `lib/queries/<resource>.ts`
- [ ] Used in a page or component
- [ ] Pytest covers the happy path and the failure paths
- [ ] `make test && make e2e` are green

### Adding a new page

- [ ] `app/<route>/page.tsx` exists and uses Server Component by
      default
- [ ] Reads from TanStack Query hooks, not direct `fetch`
- [ ] Has an empty state ("—") when there's no data
- [ ] Has an error state (not just a blank screen)
- [ ] Added to `components/sidebar.tsx`
- [ ] If it has a live count, it's wired to a query and shows as a
      badge
- [ ] Smoke-checked manually with `npm run dev` + the backend running

### Reviewing a PR

- [ ] `make test` is green in CI
- [ ] `make e2e` is green in CI
- [ ] New behaviour has tests
- [ ] Changed behaviour has updated tests
- [ ] No new dependencies without justification
- [ ] No `any` types, no `@ts-ignore`, no `eslint-disable`
- [ ] No `console.log` left in pages
- [ ] No `TODO` / `FIXME` / `XXX` left behind
- [ ] `git log --oneline | head` reads like a coherent story
