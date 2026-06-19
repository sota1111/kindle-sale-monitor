"""Unified SQLite -> Firestore mirror layer.

Cloud Run runs this app on an ephemeral container filesystem, so the SQLite
working store is wiped on every restart/redeploy. To make domain data durable we
mirror every write to Firestore and rehydrate SQLite from Firestore at startup.

Design:
- The SQLite database remains the working store (all queries/ORM code unchanged).
- On commit, inserts/updates/deletes of registered models are mirrored to Firestore,
  using the integer primary key as the Firestore document id so relational
  references (book_id, sale_history_id) stay valid across a rehydrate.
- At startup ``rehydrate_from_firestore`` reads every mirror collection back into
  SQLite (FK-safe order) before the wishlist seeding runs.

All Firestore access is best-effort: when Firestore is unconfigured (local/dev) the
mirror is a no-op and the app behaves exactly as before.
"""

import logging

from sqlalchemy import event

from app.database import SessionLocal
from app.models.book import Book
from app.models.notification import NotificationHistory
from app.models.notification_condition import NotificationCondition
from app.models.sale_history import SaleHistory
from app.models.settings import AppSettings
from app.services import firestore_repository as fsr

logger = logging.getLogger(__name__)

# model class -> Firestore collection name. Primary key column is always "id".
REGISTRY = {
    Book: "mirror_books",
    SaleHistory: "mirror_sale_history",
    NotificationHistory: "mirror_notification_history",
    NotificationCondition: "mirror_notification_conditions",
    AppSettings: "mirror_app_settings",
}

# FK-safe load order for rehydration (parents before children).
REHYDRATE_ORDER = [
    Book,
    SaleHistory,
    NotificationCondition,
    NotificationHistory,
    AppSettings,
]


def _serialize(obj) -> dict:
    """Serialize a mapped instance to a plain dict over its table columns."""
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def _record(bucket: list, op: str, obj) -> None:
    collection = REGISTRY.get(type(obj))
    if collection is None:
        return
    doc_id = getattr(obj, "id", None)
    if doc_id is None:
        return
    if op == "delete":
        bucket.append((op, collection, str(doc_id), None))
    else:
        bucket.append((op, collection, str(doc_id), _serialize(obj)))


@event.listens_for(SessionLocal, "after_flush")
def _collect_changes(session, flush_context):
    if session.info.get("fs_skip"):
        return
    bucket = session.info.setdefault("fs_pending", [])
    for obj in session.new:
        _record(bucket, "upsert", obj)
    for obj in session.dirty:
        if session.is_modified(obj, include_collections=False):
            _record(bucket, "upsert", obj)
    for obj in session.deleted:
        _record(bucket, "delete", obj)


@event.listens_for(SessionLocal, "after_commit")
def _push_changes(session):
    bucket = session.info.pop("fs_pending", None)
    if not bucket:
        return
    for op, collection, doc_id, data in bucket:
        if op == "delete":
            fsr.mirror_delete(collection, doc_id)
        else:
            fsr.mirror_upsert(collection, doc_id, data)


@event.listens_for(SessionLocal, "after_rollback")
def _discard_changes(session):
    session.info.pop("fs_pending", None)


def rehydrate_from_firestore(db) -> int:
    """Restore SQLite rows from Firestore mirror collections. Returns rows restored.

    Best-effort: never raises. Skips mirroring of its own writes via the fs_skip flag.
    """
    restored = 0
    db.info["fs_skip"] = True
    try:
        for model in REHYDRATE_ORDER:
            collection = REGISTRY[model]
            columns = {c.name for c in model.__table__.columns}
            for doc in fsr.list_collection(collection):
                if not isinstance(doc, dict):
                    continue
                # Drop unknown keys and Nones so SQLite server defaults can apply.
                kwargs = {k: v for k, v in doc.items() if k in columns and v is not None}
                if "id" not in kwargs:
                    continue
                try:
                    db.merge(model(**kwargs))
                    restored += 1
                except Exception as e:
                    logger.warning(f"Rehydrate skip {collection}/{kwargs.get('id')}: {e}")
        db.commit()
    except Exception as e:
        logger.warning(f"Firestore rehydrate failed: {e}")
        db.rollback()
    finally:
        db.info.pop("fs_skip", None)
    if restored:
        logger.info(f"Rehydrated {restored} row(s) from Firestore")
    return restored
