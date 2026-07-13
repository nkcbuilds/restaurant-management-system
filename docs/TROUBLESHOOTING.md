# Troubleshooting

Common errors and how to fix them. Organised by symptom.

---

## Setup

### `make setup` fails on Windows: "the system cannot find the file specified"

You're probably running `make` from inside Git Bash, and the recipe
tries to invoke `python.exe` with a backslash path. Run `make setup`
from the same shell you'll use for everything else (Git Bash on
Windows, or PowerShell).

If `make` is unavailable, use the PowerShell bootstrapper instead:

```powershell
.\scripts\bootstrap.ps1
```

### `npm install` fails with "engine incompatible" warnings

We pin Node 20+, npm 10+. If you're on an older Node:

```bash
node --version   # must be >= 20
npm --version    # must be >= 10
```

If you can't upgrade Node, run with `--legacy-peer-deps`:

```bash
npm install --legacy-peer-deps
```

This is what the Makefile already does, so the warning is benign.

### `pip install -r requirements-dev.txt` fails: "Python >= 3.10 required"

We require Python 3.10+. `python --version` should show 3.10, 3.11, or
3.12. The CI matrix runs against all three.

---

## Development

### Dashboard shows "Offline" but the backend is running

The dashboard reads `/api/sync/health` (a Next.js proxy). Check:

1. **Is FastAPI listening on a reachable address?** `curl
http://localhost:8000/api/health` should return `200 OK`. If it
   returns nothing or connection refused, the backend isn't up.
2. **Is `NEXT_PUBLIC_API_URL` correct?** Check `.env.local`. If
   you started the frontend before setting this, restart it.
3. **Is CORS blocking?** `CORS_ALLOW_ORIGINS` in `backend/core/__init__.py`
   must include the frontend's origin (default
   `http://localhost:3000`).
4. **Is uvicorn binding to `0.0.0.0`?** It should by default. If
   you changed it, set it back.

### `make e2e` fails with `HTTP 500 on /api/dishes: "no such table: dishes"`

This was a known bug in the auto-reloader restarting the worker mid-
request. It is **fixed**: `make e2e` always passes the
`--no-reload` flag.

If you're running the smoke against a backend you started manually,
make sure you used the same flag:

```bash
python backend/run.py --no-reload
```

If you see the error without the auto-reloader involved, check that
your `backend/restaurant.db` is writable and not held open by another
process.

### The kitchen page never updates

Kitchen polls `useKitchenTickets()` every 10 seconds. If you're not
seeing updates:

1. **Did you create an order?** Submit an order from `/orders`. It
   should appear in `/kitchen` within 10s.
2. **Is TanStack Query in error state?** Open DevTools → Network and
   look for `/api/kitchen/tickets` requests. If they're returning 403,
   you need to set `X-User-Role: kitchen` somewhere — but the
   public endpoint doesn't require a role. If they're 500, see the
   backend logs.
3. **Is the page actually mounted?** Check the URL is `/kitchen`
   exactly, not `/kitchen/`.

### `npm run dev` complains about "Cannot find module"

You probably ran `npm install` against a stale lockfile. Wipe and
reinstall:

```bash
rm -rf node_modules .next
npm install --legacy-peer-deps
```

### `pytest -q` fails with `ImportError: No module named 'core'`

The tests expect to be run from the `backend/` directory so `core/`,
`database.py`, etc. are on `sys.path`. From the project root:

```bash
cd backend && pytest -q
```

Or use the Makefile: `make test` (handles the cd for you).

---

## Testing

### A test passes locally but fails in CI

The most common cause: the test used a shared resource (the dev DB,
a port, the working directory). All backend tests should use the
`db` or `temp_db_path` fixture from `conftest.py`. Both guarantee a
fresh SQLite in `tmp_path` per test.

If a test imports `database` directly, it picks up the dev DB. Don't
do that.

### `make e2e` is flaky on Windows

Run it a few times. If it succeeds ≥ 9/10, you're fine — the
occasional failure is the smoke script's `127.0.0.1` race against
uvicorn's startup. If it fails consistently, see
[Dashboard shows "Offline"](#dashboard-shows-offline-but-the-backend-is-running)
above.

If you see a "port already in use" error, run `make stop` to kill
any leftover processes.

### Tests pass but `make build` fails

The frontend build runs the same typecheck and lint as the test
command. If they pass but build fails, the most likely cause is a
Next.js-specific lint rule that `next lint` doesn't enable. Run
`npm run build` directly to see the exact error and address it.

---

## Production-ish

### I want to run this on PostgreSQL

Phase 4. Today the schema is SQLite-flavoured: `INTEGER PRIMARY KEY
AUTOINCREMENT`, `TEXT`, `REAL`. The connection string in
`database.py` defaults to `restaurant.db`. To switch:

1. Replace the SQLite connection with `psycopg2` or `asyncpg`.
2. Change `INTEGER PRIMARY KEY AUTOINCREMENT` to `SERIAL PRIMARY KEY`.
3. Add Alembic for migrations.

Don't try this before Phase 4 — there are a few `IF NOT EXISTS`
shortcuts that won't translate cleanly.

### I want to add real auth (sessions, JWT, OAuth)

Phase 4. The current `X-User-Role` header is **dev-only**. The
infrastructure is in place:

- `_require_role()` already gates every state-changing endpoint.
- `users` table has `username`, `display_name`, `role`, `is_active`.
- `write_audit()` already records every state-changing action.

To add real auth:

1. Replace `X-User-Role` parsing in `_require_role()` with a session
   cookie / JWT decoder.
2. Add `POST /api/auth/login` that issues the token.
3. Update `useSystemHealth` and friends in the frontend to send
   `Authorization: Bearer ...` instead of the role header.

### I want to add Prometheus metrics scraping

The `/metrics` endpoint already exposes a minimal exposition. To wire
it into a real Prometheus:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: restaurantos
    metrics_path: /metrics
    static_configs:
      - targets: ["restaurantos-backend:8000"]
```

The current counters are `restaurantos_ingredients_total`,
`restaurantos_ingredients_low_stock`, `restaurantos_orders_total`.
Add more in `main.py:prometheus_metrics()` as needed.

---

## Getting help

If you're stuck and none of the above applies:

1. Search [`docs/`](.) for the topic. The README's "Documentation" section lists every doc and what it's for.
2. Look at `git log --oneline` — the commit messages narrate the
   rebuild, and `git log -p <file>` shows the discussion that landed
   each line.
3. Check `backend/restaurant_api.log` for the backend's view. Every
   500 has an `error_id` you can grep for.
4. Run `make e2e` to confirm the system is in a known-good state.
   If it passes, the problem is in your change; if it fails, the
   problem is environmental.
