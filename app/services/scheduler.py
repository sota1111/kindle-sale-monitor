import logging
from datetime import datetime

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings as app_settings

logger = logging.getLogger(__name__)

jobstores = {"default": SQLAlchemyJobStore(url=app_settings.database_url)}
scheduler = AsyncIOScheduler(jobstores=jobstores)


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


def list_jobs() -> list[dict]:
    """List all scheduled jobs."""
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "next_run_time": job.next_run_time,
            "trigger": str(job.trigger),
            "paused": job.next_run_time is None
        })
    return jobs


def get_job_info(job_id: str) -> dict | None:
    """Get detailed info for a specific job."""
    job = scheduler.get_job(job_id)
    if not job:
        return None
    return {
        "id": job.id,
        "next_run_time": job.next_run_time,
        "trigger": str(job.trigger),
        "paused": job.next_run_time is None
    }


def pause_job(job_id: str) -> bool:
    """Pause a job."""
    job = scheduler.get_job(job_id)
    if job:
        job.pause()
        logger.info(f"Job {job_id} paused")
        return True
    return False


def resume_job(job_id: str) -> bool:
    """Resume a paused job."""
    job = scheduler.get_job(job_id)
    if job:
        job.resume()
        logger.info(f"Job {job_id} resumed")
        return True
    return False


def reschedule_job(job_id: str, interval_hours: int) -> bool:
    """Reschedule a job with a new interval."""
    job = scheduler.get_job(job_id)
    if job:
        job.reschedule(trigger=IntervalTrigger(hours=interval_hours))
        logger.info(f"Job {job_id} rescheduled with interval={interval_hours}h")
        return True
    return False


def trigger_job(job_id: str) -> bool:
    """Trigger a job to run immediately."""
    job = scheduler.get_job(job_id)
    if job:
        # APScheduler 3.x: setting next_run_time to now triggers it
        job.modify(next_run_time=datetime.now(scheduler.timezone))
        logger.info(f"Job {job_id} triggered to run immediately")
        return True
    return False
