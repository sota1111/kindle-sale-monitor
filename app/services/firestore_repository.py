import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def save_sale_state(asin: str, state: dict) -> None:
    """Save latest sale state to Firestore sale_states/{asin}."""
    client = _get_client()
    if not client:
        return
    try:
        doc = client.collection("sale_states").document(asin)
        doc.set({
            "asin": asin,
            "discount_rate": state.get("discount_rate"),
            "point_rate": state.get("point_rate"),
            "cashback_info": state.get("cashback_info"),
            "sale_type": state.get("sale_type"),
            "source_url": state.get("sale_bon_url"),
            "updated_at": datetime.now(timezone.utc),
        })
    except Exception as e:
        logger.warning(f"Firestore save_sale_state failed: {e}")


def get_sale_state(asin: str) -> Optional[dict]:
    """Get latest sale state from Firestore sale_states/{asin}."""
    client = _get_client()
    if not client:
        return None
    try:
        doc = client.collection("sale_states").document(asin).get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        logger.warning(f"Firestore get_sale_state failed: {e}")
        return None


def append_sale_history(asin: str, history: dict) -> None:
    """Append a sale history entry to Firestore sale_histories collection."""
    client = _get_client()
    if not client:
        return
    try:
        client.collection("sale_histories").add({
            "asin": asin,
            "detected_at": datetime.now(timezone.utc),
            "discount_rate": history.get("discount_rate"),
            "point_rate": history.get("point_rate"),
            "cashback_info": history.get("cashback_info"),
            "sale_type": history.get("sale_type"),
            "source_url": history.get("sale_bon_url"),
        })
    except Exception as e:
        logger.warning(f"Firestore append_sale_history failed: {e}")


def append_notification(asin: str, notification: dict) -> None:
    """Append a notification record to Firestore notifications collection."""
    client = _get_client()
    if not client:
        return
    try:
        client.collection("notifications").add({
            "asin": asin,
            "notified_at": datetime.now(timezone.utc),
            "content": notification.get("content"),
            "destination": notification.get("destination", "discord"),
            "success": notification.get("success", False),
        })
    except Exception as e:
        logger.warning(f"Firestore append_notification failed: {e}")


def get_books_from_firestore() -> list:
    """Get book wishlist from Firestore books collection. Returns [] if unavailable."""
    client = _get_client()
    if not client:
        return []
    try:
        docs = client.collection("books").where("enabled", "==", True).stream()
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        logger.warning(f"Firestore get_books_from_firestore failed: {e}")
        return []


def append_monitor_log(log: dict) -> None:
    """Append a monitor-run record to Firestore monitor_logs collection.

    Cloud Run's SQLite is ephemeral, so the run history (実行履歴) is mirrored
    here to survive container restarts/redeploys. Best-effort: no-op when no
    Firestore client is configured.
    """
    client = _get_client()
    if not client:
        return
    try:
        client.collection("monitor_logs").add({
            "started_at": log.get("started_at"),
            "finished_at": log.get("finished_at"),
            "books_checked": log.get("books_checked", 0),
            "sales_found": log.get("sales_found", 0),
            "notified": log.get("notified", 0),
            "status": log.get("status"),
            "error_message": log.get("error_message"),
        })
    except Exception as e:
        logger.warning(f"Firestore append_monitor_log failed: {e}")


def list_monitor_logs(limit: int = 100) -> list:
    """List monitor-run records from Firestore, newest first. [] if unavailable."""
    client = _get_client()
    if not client:
        return []
    try:
        from google.cloud import firestore

        docs = (
            client.collection("monitor_logs")
            .order_by("started_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        logger.warning(f"Firestore list_monitor_logs failed: {e}")
        return []


def mirror_upsert(collection: str, doc_id: str, data: dict) -> None:
    """Best-effort upsert of a single document into Firestore.

    Used by the generic SQLite→Firestore mirror layer (firestore_sync) so that all
    domain data survives Cloud Run's ephemeral container filesystem. No-op when
    Firestore is not configured.
    """
    client = _get_client()
    if not client:
        return
    try:
        client.collection(collection).document(doc_id).set(data)
    except Exception as e:
        logger.warning(f"Firestore mirror_upsert failed ({collection}/{doc_id}): {e}")


def mirror_delete(collection: str, doc_id: str) -> None:
    """Best-effort delete of a single document from Firestore. No-op when unconfigured."""
    client = _get_client()
    if not client:
        return
    try:
        client.collection(collection).document(doc_id).delete()
    except Exception as e:
        logger.warning(f"Firestore mirror_delete failed ({collection}/{doc_id}): {e}")


def list_collection(collection: str) -> list:
    """Return all documents in a Firestore collection as dicts. [] if unavailable."""
    client = _get_client()
    if not client:
        return []
    try:
        return [doc.to_dict() for doc in client.collection(collection).stream()]
    except Exception as e:
        logger.warning(f"Firestore list_collection failed ({collection}): {e}")
        return []


def _get_client():
    from app.services.firestore_client import get_firestore_client
    return get_firestore_client()
