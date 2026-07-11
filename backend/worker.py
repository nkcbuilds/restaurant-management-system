"""
RestaurantOS background worker.

Phase 0: process is started but no real jobs run yet. This file exists
to (a) prove the API process no longer owns the schedule, and (b) give
operators a single entry point that future phases will fill in.

Usage:
    cd restaurant-management-system/backend
    source ../.venv/bin/activate   # or .venv\\Scripts\\activate on Windows
    python worker.py
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from datetime import datetime

from core import DEMO_MODE_ENABLED
from database import DatabaseManager

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self) -> None:
        self.db = DatabaseManager()
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        logger.info("Worker stop requested")
        self._stop.set()

    async def run_forever(self) -> None:
        logger.info("Worker started (no jobs registered yet). PID=%s", __import__("os").getpid())
        # Heartbeat every 30s so an operator can see the process is alive
        # even before any jobs land. Replaced in Phase 1 by APScheduler.
        while not self._stop.is_set():
            logger.debug(
                "worker heartbeat ts=%s demo_mode=%s",
                datetime.utcnow().isoformat(),
                DEMO_MODE_ENABLED,
            )
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                continue
        logger.info("Worker stopped cleanly")


async def _async_main(once: bool) -> int:
    worker = Worker()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.request_stop)
        except NotImplementedError:
            # Windows: signal handlers can't be added in the default loop.
            pass
    if once:
        logger.info("Worker --once: started, doing one heartbeat tick then exiting")
        await asyncio.sleep(1)
        logger.info("Worker --one done")
        return 0
    await worker.run_forever()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="RestaurantOS background worker")
    parser.add_argument(
        "--once", action="store_true", help="Run a single tick and exit (smoke test)"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    raise SystemExit(asyncio.run(_async_main(once=args.once)))


if __name__ == "__main__":
    main()
