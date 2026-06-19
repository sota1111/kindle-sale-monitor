from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.history import get_recent_monitor_logs
from app.database import Base
from app.models.log import MonitorLog
from app.services import firestore_repository as fsr

TEST_DATABASE_URL = "sqlite:///./test_firestore_monitor_logs.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# --- Minimal in-memory Firestore double ----------------------------------


class _FakeDoc:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _FakeQuery:
    def __init__(self, docs, field=None, descending=False, limit=None):
        self._docs = docs
        self._field = field
        self._descending = descending
        self._limit = limit

    def order_by(self, field, direction=None):
        descending = bool(direction) and str(direction).upper().endswith("DESCENDING")
        return _FakeQuery(self._docs, field, descending, self._limit)

    def limit(self, n):
        return _FakeQuery(self._docs, self._field, self._descending, n)

    def stream(self):
        rows = list(self._docs)
        if self._field:
            rows = sorted(rows, key=lambda d: d.get(self._field), reverse=self._descending)
        if self._limit is not None:
            rows = rows[: self._limit]
        return [_FakeDoc(d) for d in rows]


class _FakeCollection:
    def __init__(self, store):
        self._store = store

    def add(self, data):
        self._store.append(dict(data))

    def order_by(self, field, direction=None):
        return _FakeQuery(self._store).order_by(field, direction)

    def limit(self, n):
        return _FakeQuery(self._store).limit(n)

    def stream(self):
        return _FakeQuery(self._store).stream()


class _FakeClient:
    def __init__(self):
        self._collections = {}

    def collection(self, name):
        return _FakeCollection(self._collections.setdefault(name, []))


@pytest.fixture
def fake_client(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(fsr, "_get_client", lambda: client)
    return client


def _fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


# --- Tests ---------------------------------------------------------------


def test_append_and_list_monitor_logs(fake_client):
    base = datetime(2026, 1, 1, 0, 0, 0)
    fsr.append_monitor_log({
        "started_at": base,
        "finished_at": base + timedelta(seconds=5),
        "books_checked": 3,
        "sales_found": 0,
        "notified": 0,
        "status": "success",
    })
    fsr.append_monitor_log({
        "started_at": base + timedelta(hours=12),
        "finished_at": base + timedelta(hours=12, seconds=8),
        "books_checked": 3,
        "sales_found": 2,
        "notified": 1,
        "status": "success",
    })

    logs = fsr.list_monitor_logs(10)
    assert len(logs) == 2
    # Newest first.
    assert logs[0]["started_at"] == base + timedelta(hours=12)
    # A zero-sale run must still be recorded/visible.
    assert any(row["sales_found"] == 0 for row in logs)


def test_list_returns_empty_without_client(monkeypatch):
    monkeypatch.setattr(fsr, "_get_client", lambda: None)
    assert fsr.list_monitor_logs() == []
    # append must be a no-op (no exception) when Firestore is unconfigured.
    fsr.append_monitor_log({"started_at": datetime(2026, 1, 1), "status": "success"})


def test_get_recent_falls_back_to_sqlite(monkeypatch):
    # Firestore unavailable -> read durable history from SQLite.
    monkeypatch.setattr(fsr, "_get_client", lambda: None)
    db = _fresh_db()
    try:
        base = datetime(2026, 2, 1, 0, 0, 0)
        db.add(
            MonitorLog(
                started_at=base,
                finished_at=base + timedelta(seconds=3),
                books_checked=5,
                sales_found=0,
                notified=0,
                status="success",
            )
        )
        db.commit()
        rows = get_recent_monitor_logs(db, 10)
        assert len(rows) == 1
        assert rows[0].books_checked == 5
    finally:
        db.close()


def test_get_recent_prefers_firestore(fake_client):
    # When Firestore has data it is the source of truth (durable across restarts).
    base = datetime(2026, 3, 1, 0, 0, 0)
    fsr.append_monitor_log({
        "started_at": base,
        "finished_at": base,
        "books_checked": 7,
        "sales_found": 0,
        "notified": 0,
        "status": "success",
    })
    db = _fresh_db()
    try:
        rows = get_recent_monitor_logs(db, 10)
        assert len(rows) == 1
        assert rows[0].books_checked == 7
        assert rows[0].sales_found == 0
    finally:
        db.close()
