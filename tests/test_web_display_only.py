"""SOT-1299: the Web app is display + Firestore-registration only.

Research-trigger routes (check / run / scheduler) must not be mounted, while the
display routes keep responding.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite:///./test_web_display_only.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    yield
    if previous is not None:
        app.dependency_overrides[get_db] = previous
    else:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/run"),
        ("post", "/api/check"),
        ("post", "/api/check/all"),
        ("get", "/api/scheduler/jobs"),
    ],
)
def test_research_routes_not_mounted(method, path):
    resp = client.request(method.upper(), path)
    assert resp.status_code == 404, f"{method.upper()} {path} should be unmounted"


@pytest.mark.parametrize("path", ["/", "/books"])
def test_display_routes_still_respond(path):
    resp = client.get(path)
    assert resp.status_code != 404
