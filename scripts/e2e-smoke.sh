#!/usr/bin/env bash
# RestaurantOS end-to-end smoke test.
# Requires the FastAPI backend on http://localhost:8000.
# This is a thin wrapper around the cross-platform Node script.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec node "$SCRIPT_DIR/e2e-smoke.cjs" "$@"
