import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite:///./test_kindle_monitor.db"
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


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def bypass_auth(monkeypatch):
    monkeypatch.setattr("app.auth._is_exempt", lambda path: True)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_book():
    response = client.post("/api/books", json={"title": "テスト漫画", "asin": "B00TEST123"})
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "テスト漫画"
    assert data["asin"] == "B00TEST123"
    return data["id"]


def test_list_books():
    response = client.get("/api/books")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_book():
    create_resp = client.post("/api/books", json={"title": "テスト漫画2"})
    book_id = create_resp.json()["id"]
    response = client.get(f"/api/books/{book_id}")
    assert response.status_code == 200
    assert response.json()["id"] == book_id


def test_update_book():
    create_resp = client.post("/api/books", json={"title": "更新前"})
    book_id = create_resp.json()["id"]
    response = client.put(f"/api/books/{book_id}", json={"title": "更新後", "enabled": False})
    assert response.status_code == 200
    assert response.json()["title"] == "更新後"
    assert response.json()["enabled"] is False


def test_delete_book():
    create_resp = client.post("/api/books", json={"title": "削除用"})
    book_id = create_resp.json()["id"]
    response = client.delete(f"/api/books/{book_id}")
    assert response.status_code == 204


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_nonexistent_book():
    response = client.get("/api/books/99999")
    assert response.status_code == 404


def test_book_list_filter():
    client.post("/api/books", json={"title": "有効本", "enabled": True})
    client.post("/api/books", json={"title": "無効本", "enabled": False})
    response = client.get("/api/books")
    assert response.status_code == 200
    assert len(response.json()) >= 2


def test_api_book_filter():
    # Ensure we have at least one enabled and one disabled
    client.post("/api/books", json={"title": "Filter Test Enabled", "enabled": True})
    client.post("/api/books", json={"title": "Filter Test Disabled", "enabled": False})

    # Test enabled=true
    resp_enabled = client.get("/api/books?enabled=true")
    assert resp_enabled.status_code == 200
    for book in resp_enabled.json():
        assert book["enabled"] is True

    # Test enabled=false
    resp_disabled = client.get("/api/books?enabled=false")
    assert resp_disabled.status_code == 200
    for book in resp_disabled.json():
        assert book["enabled"] is False


def test_create_notification_condition():
    """Test creating a notification condition for a book."""
    # First create a book
    resp = client.post("/api/books", json={"title": "条件テスト漫画", "asin": "B00COND001"})
    assert resp.status_code == 201
    book_id = resp.json()["id"]

    # Create a condition
    cond_resp = client.post(
        f"/api/books/{book_id}/conditions",
        json={
            "name": "50%以上OFF",
            "min_discount_rate": 50,
            "cashback_only": False,
            "min_cashback_rate": None,
            "volume_filter": None,
            "cheapest_only": False,
            "free_only": False,
        },
    )
    assert cond_resp.status_code == 201
    data = cond_resp.json()
    assert data["min_discount_rate"] == 50
    assert data["book_id"] == book_id
    return book_id, data["id"]


def test_list_notification_conditions():
    """Test listing notification conditions for a book."""
    resp = client.post("/api/books", json={"title": "条件一覧テスト", "asin": "B00COND002"})
    assert resp.status_code == 201
    book_id = resp.json()["id"]

    client.post(
        f"/api/books/{book_id}/conditions",
        json={"min_discount_rate": 50},
    )
    client.post(
        f"/api/books/{book_id}/conditions",
        json={"cashback_only": True},
    )

    list_resp = client.get(f"/api/books/{book_id}/conditions")
    assert list_resp.status_code == 200
    conditions = list_resp.json()
    assert len(conditions) >= 2


def test_delete_notification_condition():
    """Test deleting a notification condition."""
    resp = client.post("/api/books", json={"title": "条件削除テスト", "asin": "B00COND003"})
    assert resp.status_code == 201
    book_id = resp.json()["id"]

    cond_resp = client.post(
        f"/api/books/{book_id}/conditions",
        json={"min_discount_rate": 30},
    )
    assert cond_resp.status_code == 201
    cond_id = cond_resp.json()["id"]

    del_resp = client.delete(f"/api/books/{book_id}/conditions/{cond_id}")
    assert del_resp.status_code == 204

    list_resp = client.get(f"/api/books/{book_id}/conditions")
    conditions = [c for c in list_resp.json() if c["id"] == cond_id]
    assert len(conditions) == 0
