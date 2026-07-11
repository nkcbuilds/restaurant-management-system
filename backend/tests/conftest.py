"""
Shared fixtures for backend tests.

Every test gets a fresh on-disk SQLite database in a temp file, so tests
do not share state and the production `restaurant.db` is never touched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make `backend/` importable as the project root so `from core import ...`
# and `from database import ...` work in tests.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture()
def temp_db_path(tmp_path):
    return str(tmp_path / "test_restaurant.db")


@pytest.fixture()
def db(temp_db_path):
    from database import DatabaseManager

    manager = DatabaseManager(temp_db_path)
    yield manager
    # Cleanup happens automatically with tmp_path; just close any open
    # connections in case a test left one dangling.
    try:
        manager.get_connection().close()
    except Exception:
        pass
