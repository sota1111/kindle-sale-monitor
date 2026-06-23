from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.book import Book
from app.models.sale_history import SaleHistory

TEST_DATABASE_URL = "sqlite:///./test_api_dashboard.db"
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
    # Bind the override at test time (not import time) so it wins regardless of
    # which other test module last set app.dependency_overrides[get_db].
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    yield
    if previous is not None:
        app.dependency_overrides[get_db] = previous


def _seed():
    db = TestingSessionLocal()
    try:
        book = Book(title="ダッシュボードテスト漫画")
        db.add(book)
        db.flush()
        base = datetime(2026, 1, 1)
        rows = [
            SaleHistory(
                book_id=book.id, price=1000, effective_price=1000, discount_rate=0,
                fetched_at=base,
            ),
            SaleHistory(
                book_id=book.id, price=1000, effective_price=700, discount_rate=30,
                is_cheapest=True, fetched_at=base + timedelta(days=1),
            ),
            SaleHistory(
                book_id=book.id, price=1000, effective_price=800, discount_rate=20,
                fetched_at=base + timedelta(days=2),
            ),
        ]
        db.add_all(rows)
        db.commit()
        return book.id
    finally:
        db.close()


def test_summary_with_data():
    _seed()
    res = client.get("/api/dashboard/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["book_count"] == 1
    assert data["sale_record_count"] == 3
    assert data["books_with_history"] == 1
    assert data["all_time_low_hits"] == 1
    # Latest row (day 2) is discounted -> on sale now.
    assert data["on_sale_now"] == 1
    # Avg of discounted rows (30, 20) = 25.0
    assert data["avg_discount_rate"] == 25.0


def test_summary_empty():
    res = client.get("/api/dashboard/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["book_count"] == 0
    assert data["sale_record_count"] == 0
    assert data["on_sale_now"] == 0
    assert data["avg_discount_rate"] == 0.0


def test_price_trends_shape():
    book_id = _seed()
    res = client.get("/api/dashboard/price-trends?limit=5")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    series = data[0]
    assert series["book_id"] == book_id
    assert series["title"] == "ダッシュボードテスト漫画"
    assert len(series["points"]) == 3
    fetched = [p["fetched_at"] for p in series["points"]]
    assert fetched == sorted(fetched)
    assert set(series["points"][0].keys()) == {"fetched_at", "price", "effective_price"}


def test_price_trends_empty():
    res = client.get("/api/dashboard/price-trends")
    assert res.status_code == 200
    assert res.json() == []
