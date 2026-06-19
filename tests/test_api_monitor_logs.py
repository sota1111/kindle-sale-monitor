from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.log import MonitorLog

TEST_DATABASE_URL = "sqlite:///./test_monitor_logs.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def bypass_auth(monkeypatch):
    monkeypatch.setattr("app.auth._is_exempt", lambda path: True)
    # Point get_db at this module's DB for the duration of each test, then
    # restore whatever override was in place so sibling test modules keep theirs.
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    yield
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


def _seed_logs():
    db = TestingSessionLocal()
    try:
        base = datetime(2026, 1, 1, 0, 0, 0)
        db.add_all(
            [
                MonitorLog(
                    started_at=base,
                    finished_at=base + timedelta(seconds=5),
                    books_checked=3,
                    sales_found=0,
                    notified=0,
                    status="success",
                ),
                MonitorLog(
                    started_at=base + timedelta(hours=12),
                    finished_at=base + timedelta(hours=12, seconds=8),
                    books_checked=3,
                    sales_found=2,
                    notified=1,
                    status="success",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()


def test_monitor_logs_includes_zero_sale_run():
    _seed_logs()
    res = client.get("/api/monitor-logs")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 2
    # A run with zero sales must still be present.
    assert any(row["sales_found"] == 0 for row in data)


def test_monitor_logs_ordered_desc():
    _seed_logs()
    res = client.get("/api/monitor-logs")
    assert res.status_code == 200
    started = [row["started_at"] for row in res.json()]
    assert started == sorted(started, reverse=True)


def test_monitor_logs_shape():
    _seed_logs()
    res = client.get("/api/monitor-logs?limit=1")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert {
        "id",
        "started_at",
        "finished_at",
        "books_checked",
        "sales_found",
        "notified",
        "status",
        "error_message",
    } <= set(data[0].keys())
