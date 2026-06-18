from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.book import Book
from app.models.sale_history import SaleHistory

TEST_DATABASE_URL = "sqlite:///./test_price_history.db"
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


def _seed_book_with_history() -> int:
    db = TestingSessionLocal()
    try:
        book = Book(title="価格推移テスト漫画")
        db.add(book)
        db.flush()
        book_id = book.id

        base = datetime(2026, 1, 1, 0, 0, 0)
        # Insert out of chronological order to verify ordering by fetched_at.
        rows = [
            SaleHistory(
                book_id=book_id,
                price=1000,
                effective_price=800,
                discount_rate=20,
                point_rate=0,
                fetched_at=base + timedelta(days=2),
            ),
            SaleHistory(
                book_id=book_id,
                price=1200,
                effective_price=1200,
                discount_rate=0,
                point_rate=0,
                fetched_at=base,
            ),
            SaleHistory(
                book_id=book_id,
                price=900,
                effective_price=700,
                discount_rate=25,
                point_rate=10,
                fetched_at=base + timedelta(days=1),
            ),
        ]
        db.add_all(rows)
        db.commit()
        return book_id
    finally:
        db.close()


def _create_empty_book() -> int:
    db = TestingSessionLocal()
    try:
        book = Book(title="履歴なし漫画")
        db.add(book)
        db.commit()
        db.refresh(book)
        return book.id
    finally:
        db.close()


def test_price_history_returns_ascending():
    book_id = _seed_book_with_history()
    res = client.get(f"/api/books/{book_id}/price-history")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 3
    fetched = [p["fetched_at"] for p in data]
    assert fetched == sorted(fetched)
    # Effective prices follow chronological order: 1200 -> 700 -> 800
    assert [p["effective_price"] for p in data] == [1200, 700, 800]


def test_price_history_shape():
    book_id = _seed_book_with_history()
    res = client.get(f"/api/books/{book_id}/price-history")
    assert res.status_code == 200
    data = res.json()
    assert data
    for point in data:
        assert set(point.keys()) == {
            "fetched_at",
            "price",
            "effective_price",
            "discount_rate",
            "point_rate",
        }


def test_price_history_empty():
    book_id = _create_empty_book()
    res = client.get(f"/api/books/{book_id}/price-history")
    assert res.status_code == 200
    assert res.json() == []
