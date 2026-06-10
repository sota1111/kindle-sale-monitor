import logging

logger = logging.getLogger(__name__)

_client = None


def get_firestore_client():
    """Return Firestore client if GOOGLE_CLOUD_PROJECT is set, else None."""
    global _client
    if _client is not None:
        return _client

    from app.config import settings

    if not settings.google_cloud_project:
        return None

    try:
        from google.cloud import firestore

        _client = firestore.Client(
            project=settings.google_cloud_project,
            database=settings.firestore_database_id,
        )
        logger.info(f"Firestore client initialized: project={settings.google_cloud_project}")
        return _client
    except Exception as e:
        logger.warning(f"Firestore client init failed: {e}")
        return None
