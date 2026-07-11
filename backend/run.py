#!/usr/bin/env python3
"""
Restaurant Management System Backend
Run this script to start the FastAPI server
"""

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
    """Main function to start the server"""
    try:
        logger.info("Starting Restaurant Management System API...")

        # Check if database directory exists
        db_dir = backend_dir / "data"
        db_dir.mkdir(exist_ok=True)

        # Start the server
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info",
            access_log=True,
            reload_dirs=[str(backend_dir)],
        )

    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
