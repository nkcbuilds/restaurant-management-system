import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


class SyncService:
    def __init__(self, db_manager, prediction_engine):
        self.db_manager = db_manager
        self.prediction_engine = prediction_engine
        self.is_running = False
        self.sync_task = None
        self.last_sync = None
        self.sync_interval = 3600  # 1 hour in seconds
        self.errors = []

    async def start_auto_sync(self):
        """Start the automatic sync service"""
        if self.is_running:
            logger.warning("Sync service is already running")
            return

        self.is_running = True
        self.sync_task = asyncio.create_task(self._sync_loop())
        logger.info("Auto-sync service started")

    async def stop_auto_sync(self):
        """Stop the automatic sync service"""
        self.is_running = False
        if self.sync_task:
            self.sync_task.cancel()
            try:
                await self.sync_task
            except asyncio.CancelledError:
                pass
        logger.info("Auto-sync service stopped")

    async def _sync_loop(self):
        """Main sync loop"""
        while self.is_running:
            try:
                await self.manual_sync()
                await asyncio.sleep(self.sync_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in sync loop: {e}")
                self.errors.append(f"{datetime.now().isoformat()}: {str(e)}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying

    async def manual_sync(self) -> dict[str, Any]:
        """Perform manual sync operation"""
        try:
            logger.info("Starting manual sync operation")
            start_time = datetime.now()

            # Sync analytics
            analytics_count = await self._sync_analytics()

            # Generate predictions for tomorrow and day after
            predictions_count = await self._sync_predictions()

            # Clean old data
            cleanup_count = await self._cleanup_old_data()

            # Update sync log
            self.last_sync = datetime.now()
            await self._log_sync_operation(
                status="success",
                records_affected=analytics_count + predictions_count + cleanup_count,
            )

            duration = (datetime.now() - start_time).total_seconds()

            result = {
                "last_sync": self.last_sync.isoformat(),
                "duration_seconds": round(duration, 2),
                "records_synced": {
                    "analytics": analytics_count,
                    "predictions": predictions_count,
                    "cleanup": cleanup_count,
                },
                "status": "success",
            }

            logger.info(f"Sync completed successfully: {result}")
            return result

        except Exception as e:
            error_msg = f"Sync failed: {str(e)}"
            logger.error(error_msg)
            self.errors.append(f"{datetime.now().isoformat()}: {error_msg}")

            await self._log_sync_operation(status="error", error_message=error_msg)

            raise e

    async def _sync_analytics(self) -> int:
        """Sync and cache analytics data"""
        try:
            # Get yesterday's data and cache it
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

            # This would typically involve complex analytics calculations
            # For now, we'll just ensure the data is properly structured
            sales_data = self.db_manager.get_daily_sales(yesterday)

            if sales_data:
                logger.info(f"Analytics synced for {yesterday}")
                return 1

            return 0

        except Exception as e:
            logger.error(f"Error syncing analytics: {e}")
            raise e

    async def _sync_predictions(self) -> int:
        """Generate and sync prediction data"""
        try:
            predictions_generated = 0

            # Generate predictions for next 3 days
            for days_ahead in range(1, 4):
                target_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

                try:
                    result = await self.prediction_engine.generate_predictions(target_date)
                    predictions_generated += result.get("predictions_generated", 0)
                except Exception as e:
                    logger.error(f"Error generating predictions for {target_date}: {e}")
                    continue

            logger.info(f"Generated {predictions_generated} predictions")
            return predictions_generated

        except Exception as e:
            logger.error(f"Error syncing predictions: {e}")
            raise e

    async def _cleanup_old_data(self) -> int:
        """Clean up old data to maintain performance"""
        try:
            cleanup_count = 0

            # Clean old predictions (older than 30 days)
            cutoff_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

            conn = self.db_manager.get_connection()
            cursor = conn.cursor()

            try:
                # Clean old predictions
                cursor.execute(
                    """
                    DELETE FROM predictions WHERE prediction_date < ?
                """,
                    (cutoff_date,),
                )
                cleanup_count += cursor.rowcount

                # Clean old inventory transactions (older than 90 days)
                old_transaction_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
                cursor.execute(
                    """
                    DELETE FROM inventory_transactions WHERE DATE(timestamp) < ?
                """,
                    (old_transaction_date,),
                )
                cleanup_count += cursor.rowcount

                # Clean old sync logs (older than 30 days)
                cursor.execute(
                    """
                    DELETE FROM sync_log WHERE DATE(timestamp) < ?
                """,
                    (cutoff_date,),
                )
                cleanup_count += cursor.rowcount

                conn.commit()

            finally:
                conn.close()

            if cleanup_count > 0:
                logger.info(f"Cleaned up {cleanup_count} old records")

            return cleanup_count

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            raise e

    async def _log_sync_operation(
        self, status: str, records_affected: int = 0, error_message: str | None = None
    ):
        """Log sync operation to database"""
        try:
            conn = self.db_manager.get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO sync_log (sync_type, status, records_affected, error_message)
                VALUES (?, ?, ?, ?)
            """,
                ("auto_sync", status, records_affected, error_message),
            )

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Error logging sync operation: {e}")

    def get_status(self) -> dict[str, Any]:
        """Get current sync service status"""
        return {
            "is_running": self.is_running,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "sync_interval_minutes": self.sync_interval // 60,
            "recent_errors": self.errors[-5:] if self.errors else [],
            "total_errors": len(self.errors),
        }

    def set_sync_interval(self, minutes: int):
        """Set the sync interval in minutes"""
        if minutes < 1:
            raise ValueError("Sync interval must be at least 1 minute")

        self.sync_interval = minutes * 60
        logger.info(f"Sync interval set to {minutes} minutes")
