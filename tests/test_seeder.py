import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.book import Book
from app.services.seeder import seed_books_from_wishlist

TEST_DATABASE_URL = "sqlite:///./test_seeder.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def _write_wishlist(tmp_path):
    entries = [
        {"title": "鋼の錬金術師", "author": "荒川弘", "publisher": "スクウェア・エニックス"},
        {"title": "BLUE GIANT", "author": "石塚真一", "publisher": "小学館"},
        {"title": "クロサギ", "author": "黒丸 / 夏原武", "publisher": "小学館"},
    ]
    path = tmp_path / "wishlist.json"
    path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_seed_inserts_all(tmp_path):
    db = _fresh_db()
    try:
        path = _write_wishlist(tmp_path)
        inserted = seed_books_from_wishlist(db, path)
        assert inserted == 3
        assert db.query(Book).count() == 3
    finally:
        db.close()


def test_seed_is_idempotent(tmp_path):
    db = _fresh_db()
    try:
        path = _write_wishlist(tmp_path)
        assert seed_books_from_wishlist(db, path) == 3
        # Running again must not duplicate.
        assert seed_books_from_wishlist(db, path) == 0
        assert db.query(Book).count() == 3
    finally:
        db.close()


def test_seed_does_not_touch_existing(tmp_path):
    db = _fresh_db()
    try:
        existing = Book(title="鋼の錬金術師", author="荒川弘", note="手動登録")
        db.add(existing)
        db.commit()

        path = _write_wishlist(tmp_path)
        inserted = seed_books_from_wishlist(db, path)
        # The duplicate title+author is skipped; the other two are added.
        assert inserted == 2
        kept = db.query(Book).filter(Book.title == "鋼の錬金術師").all()
        assert len(kept) == 1
        assert kept[0].note == "手動登録"
    finally:
        db.close()


def test_seed_missing_file_is_safe():
    db = _fresh_db()
    try:
        assert seed_books_from_wishlist(db, "/nonexistent/wishlist.json") == 0
    finally:
        db.close()
