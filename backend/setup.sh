#!/bin/bash
# Setup script for the RestaurantOS backend.
#
# Creates a .venv (hidden) virtual environment in backend/.venv, installs
# runtime + dev requirements, and is safe to re-run.
#
# Usage:
#   cd restaurant-management-system/backend
#   bash setup.sh                # uses python3
#   PYTHON=python3.11 bash setup.sh

set -euo pipefail

PYTHON="${PYTHON:-python3}"

# --- version check ----------------------------------------------------------
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Error: $PYTHON not found on PATH." >&2
  exit 1
fi
version="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
required="3.10"
if [ "$(printf '%s\n' "$required" "$version" | sort -V | head -n1)" != "$required" ]; then
  echo "Error: Python $required or higher is required (found $version)." >&2
  exit 1
fi
echo "Python version check passed: $version"

# --- virtualenv --------------------------------------------------------------
VENV_DIR=".venv"
if [ -d "$VENV_DIR" ]; then
  echo "Reusing existing virtual environment at $VENV_DIR"
else
  echo "Creating virtual environment at $VENV_DIR..."
  "$PYTHON" -m venv "$VENV_DIR"
fi

# --- activate ---------------------------------------------------------------
# shellcheck disable=SC1091
if [ -f "$VENV_DIR/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
elif [ -f "$VENV_DIR/Scripts/activate" ]; then
  # Windows
  # shellcheck disable=SC1091
  source "$VENV_DIR/Scripts/activate"
else
  echo "Error: could not find $VENV_DIR/{bin,Scripts}/activate" >&2
  exit 1
fi

# --- pip --------------------------------------------------------------------
echo "Upgrading pip..."
python -m pip install --upgrade pip

echo "Installing runtime dependencies..."
python -m pip install -r requirements.txt

if [ -f requirements-dev.txt ]; then
  echo "Installing dev dependencies (pytest, httpx, ...)..."
  python -m pip install -r requirements-dev.txt
fi

# --- data dir ---------------------------------------------------------------
mkdir -p data

# --- permissions ------------------------------------------------------------
chmod +x run.py worker.py 2>/dev/null || true

cat <<'NEXT'

Setup complete.

To start the API:
    source .venv/bin/activate   # or .venv\Scripts\activate on Windows
    python run.py               # serves on http://localhost:8000

To start the background worker (Phase 0: heartbeat only):
    python worker.py

To run the test suite:
    pytest -q

NEXT
