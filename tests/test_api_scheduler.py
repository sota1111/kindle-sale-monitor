import importlib
import os
import tempfile
from pathlib import Path

import pytest
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from fastapi.testclient import TestClient

_test_db_dir = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_test_db_dir.name) / 'app.db'}"

app = importlib.import_module("app.main").app
scheduler_service = importlib.import_module("app.services.scheduler")
scheduler = scheduler_service.scheduler


async def noop_check_job():
    return None


@pytest.fixture
def scheduler_client(tmp_path, monkeypatch):
    """Run scheduler API tests against an isolated jobstore and no-op job body."""

    if scheduler.running:
        scheduler.shutdown(wait=False)
    scheduler.configure(
        jobstores={"default": SQLAlchemyJobStore(url=f"sqlite:///{tmp_path / 'scheduler_jobs.db'}")}
    )
    monkeypatch.setattr(scheduler_service, "_check_job", noop_check_job)

    with TestClient(app) as client:
        yield client

    if scheduler.running:
        scheduler.shutdown(wait=False)


@pytest.fixture(autouse=True)
def bypass_auth(monkeypatch):
    monkeypatch.setattr("app.auth._is_exempt", lambda path: True)


def test_scheduler_persistence_config():
    """Verify that SQLAlchemyJobStore is configured as the default jobstore."""
    assert "default" in scheduler._jobstores
    assert isinstance(scheduler._jobstores["default"], SQLAlchemyJobStore)


def test_list_jobs(scheduler_client):
    """Test GET /api/scheduler/jobs."""
    response = scheduler_client.get("/api/scheduler/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert isinstance(jobs, list)
    # The kindle_check job should be there because lifespan starts it
    assert any(job["id"] == "kindle_check" for job in jobs)


def test_get_job_detail(scheduler_client):
    """Test GET /api/scheduler/jobs/{job_id}."""
    response = scheduler_client.get("/api/scheduler/jobs/kindle_check")
    assert response.status_code == 200
    job = response.json()
    assert job["id"] == "kindle_check"
    assert "next_run_time" in job
    assert "trigger" in job
    assert "paused" in job


def test_pause_resume_job(scheduler_client):
    """Test POST /api/scheduler/jobs/{job_id}/pause and resume."""
    response = scheduler_client.post("/api/scheduler/jobs/kindle_check/pause")
    assert response.status_code == 200

    response = scheduler_client.get("/api/scheduler/jobs/kindle_check")
    assert response.json()["paused"] is True

    response = scheduler_client.post("/api/scheduler/jobs/kindle_check/resume")
    assert response.status_code == 200

    response = scheduler_client.get("/api/scheduler/jobs/kindle_check")
    assert response.json()["paused"] is False


def test_reschedule_job(scheduler_client):
    """Test POST /api/scheduler/jobs/{job_id}/reschedule."""
    response = scheduler_client.post(
        "/api/scheduler/jobs/kindle_check/reschedule",
        json={"interval_hours": 6},
    )
    assert response.status_code == 200

    response = scheduler_client.get("/api/scheduler/jobs/kindle_check")
    assert "6:00:00" in response.json()["trigger"]


def test_run_job_now(scheduler_client):
    """Test POST /api/scheduler/jobs/{job_id}/run."""
    response = scheduler_client.post("/api/scheduler/jobs/kindle_check/run")
    assert response.status_code == 200


def test_run_paused_job_now(scheduler_client):
    """Test triggering a paused job whose next_run_time is None."""
    response = scheduler_client.post("/api/scheduler/jobs/kindle_check/pause")
    assert response.status_code == 200

    response = scheduler_client.post("/api/scheduler/jobs/kindle_check/run")
    assert response.status_code == 200


def test_job_not_found(scheduler_client):
    """Test 404 for non-existent job."""
    response = scheduler_client.get("/api/scheduler/jobs/non_existent")
    assert response.status_code == 404
