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


def _get_client():
    from app.services.firestore_client import get_firestore_client
    return get_firestore_client()
