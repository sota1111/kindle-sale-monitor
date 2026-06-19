"""Tests for the unified SQLite -> Firestore mirror layer (SOT-830)."""

import pytest
from sqlalchemy import create_engine

import app.database as database
from app.database import Base
from app.models.book import Book
from app.services import firestore_repository as fsr
from app.services import firestore_sync

# --- Minimal in-memory Firestore double (document-oriented) ----------------


class _FakeDoc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)

    @property
    def exists(self):
        return self._data is not None


class _FakeDocRef:
    def __init__(self, store, doc_id):
        self._store = store
        self._id = doc_id

    def set(self, data):
        self._store[self._id] = dict(data)

    def delete(self):
        self._store.pop(self._id, None)

    def get(self):
        return _FakeDoc(self._id, self._store.get(self._id))


class _FakeCollection:
    def __init__(self, store):
        self._store = store

    def document(self, doc_id):
        return _FakeDocRef(self._store, doc_id)

    def stream(self):
        return [_FakeDoc(k, v) for k, v in self._store.items()]


class _FakeClient:
    def __init__(self):
        self._collections = {}

    def collection(self, name):
        return _FakeCollection(self._collections.setdefault(name, {}))


@pytest.fixture
def fake_client(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(fsr, "_get_client", lambda: client)
    return client


@pytest.fixture
def sqlite_session(monkeypatch):
    """A throwaway SQLite session bound to the real SessionLocal class so the
    module-level event listeners fire."""
    engine = create_engine(
        "sqlite:///./test_firestore_sync.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    # Rebind the shared SessionLocal (listeners are attached to this class).
    original_bind = database.engine
    database.SessionLocal.configure(bind=engine)
    session = database.SessionLocal()
    yield session
    session.close()
    database.SessionLocal.configure(bind=original_bind)


# --- Tests ----------------------------------------------------------------


def test_commit_mirrors_book_to_firestore(fake_client, sqlite_session):
    book = Book(title="ミラー本", asin="B000TEST")
    sqlite_session.add(book)
    sqlite_session.commit()

    docs = fsr.list_collection("mirror_books")
    assert len(docs) == 1
    assert docs[0]["title"] == "ミラー本"
    assert docs[0]["asin"] == "B000TEST"
    # Document id is the SQLite primary key.
    coll = fake_client._collections["mirror_books"]
    assert str(book.id) in coll


def test_delete_mirrors_removal(fake_client, sqlite_session):
    book = Book(title="消す本")
    sqlite_session.add(book)
    sqlite_session.commit()
    book_id = book.id
    assert str(book_id) in fake_client._collections["mirror_books"]

    sqlite_session.delete(book)
    sqlite_session.commit()
    assert str(book_id) not in fake_client._collections["mirror_books"]


def test_rehydrate_restores_books(fake_client, sqlite_session):
    # Seed Firestore directly, leaving SQLite empty.
    fsr.mirror_upsert("mirror_books", "5", {"id": 5, "title": "復元される本", "enabled": True})
    assert sqlite_session.query(Book).count() == 0

    restored = firestore_sync.rehydrate_from_firestore(sqlite_session)
    assert restored == 1
    book = sqlite_session.query(Book).filter(Book.id == 5).first()
    assert book is not None
    assert book.title == "復元される本"


def test_mirror_is_noop_without_client(monkeypatch, sqlite_session):
    monkeypatch.setattr(fsr, "_get_client", lambda: None)
    book = Book(title="Firestore無効")
    sqlite_session.add(book)
    sqlite_session.commit()  # must not raise
    assert firestore_sync.rehydrate_from_firestore(sqlite_session) == 0
