#!/usr/bin/env python3
"""
Restaurant Management System Backend
Run this script to start the FastAPI server.

Usage:
    python run.py             # dev mode (auto-reload, watches *.py)
    python run.py --no-reload # CI / smoke-test mode (single process)
"""

import argparse
import logging
import sys
from pathlib import Path

import uvicorn

# Add the backend directory to Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("restaurant_api.log"), logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="RestaurantOS FastAPI backend")
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Disable uvicorn's auto-reloader (recommended for tests / CI).",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    args = parser.parse_args()

    try:
        logger.info("Starting Restaurant Management System API...")

        # Check if database directory exists
        db_dir = backend_dir / "data"
        db_dir.mkdir(exist_ok=True)

        if args.no_reload:
            # Single-process mode for CI / smoke tests. Predictable, no
            # reload-mid-request races against the SQLite file.
            uvicorn.run(
                "main:app",
                host=args.host,
                port=args.port,
                reload=False,
                log_level="info",
                access_log=True,
            )
            return

        # Dev mode with auto-reload.
        # `reload_excludes` keeps the SQLite file and the heavy directories
        # out of watchfiles' watched paths so an unrelated write to
        # restaurant.db / .venv / __pycache__ doesn't trigger a restart.
        uvicorn.run(
            "main:app",
            host=args.host,
            port=args.port,
            reload=True,
            log_level="info",
            access_log=True,
            reload_dirs=[str(backend_dir)],
            reload_excludes=[
                str(backend_dir / "*.db"),
                str(backend_dir / "*.db-*"),
                str(backend_dir / ".venv"),
                str(backend_dir / "__pycache__"),
                str(backend_dir / "tests"),
                str(backend_dir / "*.log"),
                str(backend_dir / ".pytest_cache"),
            ],
        )

    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
