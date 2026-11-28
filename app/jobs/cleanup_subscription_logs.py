from datetime import datetime, timedelta

from app import logger, scheduler
from app.db import GetDB, crud
from config import SUB_LOG_RETENTION_DAYS


def cleanup_subscription_logs():
    with GetDB() as db:
        deleted = crud.delete_old_subscription_logs(
            db, datetime.utcnow() - timedelta(days=SUB_LOG_RETENTION_DAYS))
    if deleted:
        logger.info(f"Deleted {deleted} subscription log rows older than {SUB_LOG_RETENTION_DAYS} days")


if SUB_LOG_RETENTION_DAYS > 0:
    scheduler.add_job(cleanup_subscription_logs, 'interval', coalesce=True, hours=6, max_instances=1)
