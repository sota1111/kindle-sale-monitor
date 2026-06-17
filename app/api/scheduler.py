from fastapi import APIRouter, HTTPException

from app.schemas.scheduler import JobInfo, RescheduleRequest
from app.services import scheduler as scheduler_service

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


@router.get("/jobs", response_model=list[JobInfo])
def list_jobs():
    """List all scheduled jobs."""
    return scheduler_service.list_jobs()


@router.get("/jobs/{job_id}", response_model=JobInfo)
def get_job(job_id: str):
    """Get info for a specific job."""
    job_info = scheduler_service.get_job_info(job_id)
    if not job_info:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job_info


@router.post("/jobs/{job_id}/pause")
def pause_job(job_id: str):
    """Pause a job."""
    if not scheduler_service.pause_job(job_id):
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return {"message": f"Job {job_id} paused"}


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: str):
    """Resume a job."""
    if not scheduler_service.resume_job(job_id):
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return {"message": f"Job {job_id} resumed"}


@router.post("/jobs/{job_id}/reschedule")
def reschedule_job(job_id: str, request: RescheduleRequest):
    """Reschedule a job."""
    if not scheduler_service.reschedule_job(job_id, request.interval_hours):
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return {"message": f"Job {job_id} rescheduled to {request.interval_hours}h"}


@router.post("/jobs/{job_id}/run")
def trigger_job(job_id: str):
    """Trigger a job to run immediately."""
    if not scheduler_service.trigger_job(job_id):
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return {"message": f"Job {job_id} triggered"}
