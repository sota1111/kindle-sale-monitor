from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.book import Book
from app.models.sale_history import SaleHistory
from app.services.sample_data import SAMPLE_SALE_TYPE, seed_sample_data

TEST_DATABASE_URL = "sqlite:///./test_sample_data.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def test_seed_inserts_sample_rows():
    db = _fresh_db()
    try:
        result = seed_sample_data(db)
        assert result["books"] > 0
        assert result["sale_history_rows"] > 0
        # Every generated row is tagged as sample.
        total = db.query(SaleHistory).count()
        samples = db.query(SaleHistory).filter(SaleHistory.sale_type == SAMPLE_SALE_TYPE).count()
        assert total == samples == result["sale_history_rows"]
        # Each sample book has an all-time-low marker.
        assert db.query(SaleHistory).filter(SaleHistory.is_cheapest.is_(True)).count() >= 1
    finally:
        db.close()


def test_seed_is_idempotent():
    db = _fresh_db()
    try:
        first = seed_sample_data(db)
        rows_after_first = db.query(SaleHistory).count()
        # Second run adds nothing.
        second = seed_sample_data(db)
        assert second["books"] == 0
        assert second["sale_history_rows"] == 0
        assert db.query(SaleHistory).count() == rows_after_first == first["sale_history_rows"]
    finally:
        db.close()


def test_force_regenerates_without_duplicating():
    db = _fresh_db()
    try:
        seed_sample_data(db)
        count_before = db.query(SaleHistory).count()
        books_before = db.query(Book).count()
        forced = seed_sample_data(db, force=True)
        assert forced["books"] > 0
        # Same number of rows/books — regenerated, not duplicated.
        assert db.query(SaleHistory).count() == count_before
        assert db.query(Book).count() == books_before
    finally:
        db.close()


def test_seed_does_not_touch_non_sample_rows():
    db = _fresh_db()
    try:
        book = Book(title="既存の本", author="著者")
        db.add(book)
        db.flush()
        real_row = SaleHistory(
            book_id=book.id, sale_type="paapi", price=999, effective_price=999
        )
        db.add(real_row)
        db.commit()

        seed_sample_data(db, force=True)

        kept = db.query(SaleHistory).filter(SaleHistory.sale_type == "paapi").all()
        assert len(kept) == 1
        assert kept[0].price == 999
    finally:
        db.close()
