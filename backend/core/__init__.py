"""
Core utilities and configuration for the RestaurantOS backend.
"""

from __future__ import annotations

import logging
import os
import uuid

logger = logging.getLogger(__name__)


def getenv_str(key: str, default: str | None = None) -> str | None:
    val = os.environ.get(key)
    if val is None or val == "":
        return default
    return val


def getenv_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    if val is None or val == "":
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        logger.warning("Invalid int for env %s=%r, using default %s", key, val, default)
        return default


def getenv_float(key: str, default: float) -> float:
    val = os.environ.get(key)
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        logger.warning("Invalid float for env %s=%r, using default %s", key, val, default)
        return default


def getenv_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


# Database
DB_PATH = getenv_str("RESTAURANT_DB_PATH", "restaurant.db")

# Tax: stored as a fraction (0.05 = 5%)
DEFAULT_TAX_RATE = getenv_float("RESTAURANT_TAX_RATE", 0.0)

# Idempotency
IDEMPOTENCY_REQUIRED = getenv_bool("RESTAURANT_REQUIRE_IDEMPOTENCY_KEY", True)

# CORS
CORS_ALLOW_ORIGINS: list[str] = [
    o.strip()
    for o in (
        getenv_str("CORS_ALLOW_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000") or ""
    ).split(",")
    if o.strip()
]

# Demo mode (server-side, controls whether /api/demo/seed is enabled and
# whether a 'demo' tag is allowed on rows)
DEMO_MODE_ENABLED = getenv_bool("RESTAURANT_DEMO_MODE", False)


def new_error_id() -> str:
    """Short, log-friendly error identifier returned to API consumers."""
    return uuid.uuid4().hex[:12]
