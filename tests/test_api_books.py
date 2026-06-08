from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite:///./test_kindle_monitor.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


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
