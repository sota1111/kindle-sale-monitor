import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _check_job():
    """Periodic check job executed by APScheduler."""
    from app.database import SessionLocal
    from app.services.checker import run_check_all

    db = SessionLocal()
    try:
        logger.info("Scheduled check starting...")
        result = run_check_all(db)
        logger.info(f"Scheduled check complete: {result}")
    except Exception as e:
        logger.error(f"Scheduled check failed: {e}")
    finally:
        db.close()


def start_scheduler(app, interval_hours: int = 12) -> None:
    """
    Start the APScheduler with a periodic check job.
    interval_hours: how often to run the check (default 12 hours).
    """
    if scheduler.running:
        logger.info("Scheduler already running, skipping start")
        return

    scheduler.add_job(
        _check_job,
        trigger=IntervalTrigger(hours=interval_hours),
        id="kindle_check",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info(f"Scheduler started with interval={interval_hours}h")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def update_interval(interval_hours: int) -> None:
    """Update the check interval at runtime."""
    if not scheduler.running:
        return
    job = scheduler.get_job("kindle_check")
    if job:
        job.reschedule(trigger=IntervalTrigger(hours=interval_hours))
        logger.info(f"Scheduler interval updated to {interval_hours}h")
