#!/usr/bin/env bash
# RestaurantOS end-to-end smoke (POSIX).
#
# Boots the FastAPI backend, waits for /api/health to respond, runs the
# Node smoke script, then tears the backend down. Designed to be called
# from `make e2e` (or directly from CI).
#
# Usage:
#   bash scripts/e2e.sh
#
# Environment:
#   API_URL  - override the backend URL (default: http://localhost:8000)
#   PORT     - override the backend port (default: 8000)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

API_URL="${API_URL:-http://localhost:${PORT:-8000}}"
PORT="${PORT:-8000}"

VENV_PY="backend/.venv/bin/python"
VENV_PY_WIN_ABS="$REPO_ROOT/backend/.venv/Scripts/python.exe"
VENV_PY_WIN_REL="backend/.venv/Scripts/python.exe"
if [ -x "$VENV_PY" ] && [ "$(uname -s)" != "MINGW"* ] && [ "$(uname -s)" != "MSYS"* ]; then
  : # POSIX path is fine on a POSIX host.
elif [ -x "$VENV_PY_WIN_ABS" ]; then
  # Windows under Git Bash / MSYS / WSL. cygpath makes the Windows
  # python executable callable from the bash recipe.
  VENV_PY="$(cygpath -u "$VENV_PY_WIN_ABS")"
elif [ -x "$VENV_PY_WIN_REL" ]; then
  VENV_PY="$VENV_PY_WIN_REL"
else
  echo "Error: virtualenv python not found (tried $VENV_PY, $VENV_PY_WIN_REL). Run 'make setup' first." >&2
  exit 1
fi

LOG="$(mktemp -t restaurantos-backend.XXXXXX.log)"

echo "==> Starting backend on $API_URL (log: $LOG)"
cd backend
# --no-reload runs in a single process so the auto-reloader cannot
# restart the worker mid-request while the SQLite file is being
# written. The e2e smoke doesn't need hot reload.
"$VENV_PY" run.py --no-reload >"$LOG" 2>&1 &
BACKEND_PID=$!
cd "$REPO_ROOT"

cleanup() {
  local rc=$?
  if kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "==> Stopping backend (pid $BACKEND_PID)"
    kill "$BACKEND_PID" 2>/dev/null || true
    # Give it up to 5s to exit cleanly.
    for _ in 1 2 3 4 5; do
      kill -0 "$BACKEND_PID" 2>/dev/null || break
      sleep 1
    done
    kill -9 "$BACKEND_PID" 2>/dev/null || true
  fi
  # Wait for the port to release so the next run isn't "address already
  # in use".
  sleep 1
  # Only remove the dev DB AFTER the backend has fully exited. Deleting
  # it while the auto-reloader is running triggers a restart mid-request.
  rm -f backend/restaurant.db
  exit "$rc"
}
trap cleanup EXIT INT TERM

echo "==> Waiting for $API_URL/api/health"
UP=0
for i in $(seq 1 20); do
  if curl -fs "$API_URL/api/health" >/dev/null 2>&1; then
    echo "    backend up after ${i}s"
    UP=1
    break
  fi
  sleep 1
done

if [ "$UP" -ne 1 ]; then
  echo "Error: backend did not become healthy within 20s" >&2
  echo "---- backend log ----" >&2
  cat "$LOG" >&2
  exit 1
fi

echo "==> Running e2e smoke"
API_URL="$API_URL" node scripts/e2e-smoke.cjs
