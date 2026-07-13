# RestaurantOS — top-level Makefile
#
# Goal: a fresh checkout can go from `git clone` to a green CI
# snapshot with a single command:
#
#     make setup && make test
#
# Targets are intentionally idempotent. Re-running `make setup` won't
# reinstall what's already there.
#
# Windows note: this file uses POSIX shell syntax. The repo ships
# scripts/bootstrap.ps1 for Windows users without GNU make.

# ---- Configuration -----------------------------------------------------

PYTHON        ?= python3
ifeq ($(OS),Windows_NT)
  PYTHON      := python
endif

# Repository layout.
BACKEND_DIR   := backend
VENV          := $(BACKEND_DIR)/.venv
VENV_PY       := $(VENV)/bin/python
ifeq ($(OS),Windows_NT)
  VENV_PY     := $(VENV)/Scripts/python.exe
  # mingw32-make prints `VENV_PY` with backslashes which Git Bash can't
  # execute. Convert to a POSIX path once, here, and use that everywhere
  # in the recipes.
  VENV_PY_BASH := $(shell cygpath -u "$(abspath $(VENV_PY))")
endif

API_URL       ?= http://localhost:8000

# Paths npm/Node must know about.
NPM           ?= npm

# ---- Phony targets ------------------------------------------------------

.PHONY: help setup dev backend frontend worker stop test test-backend \
        test-frontend test-e2e lint format build clean ci

# ---- Help (default) ----------------------------------------------------

help:                       ## Show this help message
	@echo "RestaurantOS — available targets:"
	@echo
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "Common flows:"
	@echo "  make setup     # install frontend + backend deps"
	@echo "  make test      # run every quality gate"
	@echo "  make dev       # start backend + frontend (Ctrl-C to stop)"
	@echo "  make ci        # what CI runs on every PR"

# ---- Setup -------------------------------------------------------------

setup:                       ## Install frontend + backend + worker deps
	@echo "==> Installing frontend dependencies"
	$(NPM) ci --legacy-peer-deps
	@echo "==> Creating backend virtualenv at $(VENV)"
	@if [ ! -d "$(VENV)" ]; then $(PYTHON) -m venv $(VENV); else echo "    (reusing existing venv)"; fi
	@echo "==> Installing backend runtime + dev dependencies"
ifeq ($(OS),Windows_NT)
	"$(VENV_PY_BASH)" -m pip install --upgrade pip
	"$(VENV_PY_BASH)" -m pip install -r $(BACKEND_DIR)/requirements-dev.txt
	"$(VENV_PY_BASH)" -m pip install -r $(BACKEND_DIR)/requirements-lint.txt
else
	$(VENV_PY) -m pip install --upgrade pip
	$(VENV_PY) -m pip install -r $(BACKEND_DIR)/requirements-dev.txt
	$(VENV_PY) -m pip install -r $(BACKEND_DIR)/requirements-lint.txt
endif
	@echo
	@echo "Setup complete. Next:"
	@echo "  make test    # run the full test suite"
	@echo "  make dev     # start the dev servers"

# ---- Test --------------------------------------------------------------

test: test-frontend test-backend   ## Run every test + lint gate
	@echo
	@echo "All checks green."

test-frontend:                ## Frontend tests (vitest)
	$(NPM) run typecheck
	$(NPM) run lint
	$(NPM) run format:check
	$(NPM) test

test-backend:                 ## Backend tests (pytest)
	@if [ ! -d "$(VENV)" ]; then echo "Run 'make setup' first."; exit 1; fi
ifeq ($(OS),Windows_NT)
	"$(VENV_PY_BASH)" -m pytest -q
else
	$(VENV_PY) -m pytest -q
endif

test-e2e:                     ## End-to-end smoke against a running backend
	@echo "Make sure the backend is running on $(API_URL) (try \`make dev\`)."
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
	  if curl -fs $(API_URL)/api/health >/dev/null 2>&1; then break; fi; \
	  echo "  waiting for $(API_URL)/api/health (attempt $$i/10)..."; \
	  sleep 1; \
	done
	API_URL=$(API_URL) node scripts/e2e-smoke.cjs

e2e:                          ## Boot backend, run smoke, tear down (uses scripts/e2e.*)
ifeq ($(OS),Windows_NT)
	@powershell -NoProfile -ExecutionPolicy Bypass -File scripts/e2e.ps1
else
	@bash scripts/e2e.sh
endif

# ---- Lint + format -----------------------------------------------------

lint:                         ## Run all linters
	$(NPM) run lint
	@if [ -d "$(VENV)" ]; then \
	  if "$(VENV_PY_BASH)" -c 'import ruff' 2>/dev/null; then \
	    "$(VENV_PY_BASH)" -m ruff check $(BACKEND_DIR); \
	  else \
	    echo "(ruff not installed; run 'make setup' or 'pip install -r backend/requirements-lint.txt')"; \
	  fi; \
	fi

format:                       ## Auto-format frontend + backend
	$(NPM) run format
	@if [ -d "$(VENV)" ]; then \
	  if "$(VENV_PY_BASH)" -c 'import ruff' 2>/dev/null; then \
	    "$(VENV_PY_BASH)" -m ruff format $(BACKEND_DIR); \
	  else \
	    echo "(ruff not installed; run 'make setup' or 'pip install -r backend/requirements-lint.txt')"; \
	  fi; \
	fi

# ---- Build -------------------------------------------------------------

build:                        ## Production build of the frontend
	$(NPM) run build

# ---- Dev (run both servers) -------------------------------------------

dev:                          ## Run backend + frontend together (Ctrl-C stops both)
	@trap 'kill 0' EXIT; \
	  (cd $(BACKEND_DIR) && $(VENV_PY) run.py) & \
	  $(NPM) run dev

backend:                      ## Run only the FastAPI backend
	@if [ ! -d "$(VENV)" ]; then echo "Run 'make setup' first."; exit 1; fi
ifeq ($(OS),Windows_NT)
	cd $(BACKEND_DIR) && "$(VENV_PY_BASH)" run.py
else
	cd $(BACKEND_DIR) && $(VENV_PY) run.py
endif

frontend:                     ## Run only the Next.js dev server
	$(NPM) run dev

worker:                       ## Run the background worker (separate process)
	@if [ ! -d "$(VENV)" ]; then echo "Run 'make setup' first."; exit 1; fi
ifeq ($(OS),Windows_NT)
	cd $(BACKEND_DIR) && "$(VENV_PY_BASH)" worker.py
else
	cd $(BACKEND_DIR) && $(VENV_PY) worker.py
endif

stop:                         ## Kill any uvicorn / next dev servers still running
	-@taskkill /F /IM uvicorn.exe 2>/dev/null || true
	-@taskkill /F /IM node.exe    2>/dev/null || true
	-@pkill -f "uvicorn" 2>/dev/null || true
	-@pkill -f "next dev" 2>/dev/null || true

# ---- CI mirror ---------------------------------------------------------

ci:                           ## Mirror .github/workflows/ci.yml locally
	make lint
	make test
	make build

# ---- Clean -------------------------------------------------------------

clean:                        ## Remove build artifacts, caches, dev DB
	rm -rf .next out node_modules
	rm -rf $(VENV) $(BACKEND_DIR)/__pycache__ $(BACKEND_DIR)/core/__pycache__ $(BACKEND_DIR)/tests/__pycache__
	rm -f $(BACKEND_DIR)/restaurant.db $(BACKEND_DIR)/restaurant_api.log
	@echo "Cleaned."
