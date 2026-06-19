import logging

logger = logging.getLogger(__name__)

_client = None


def get_firestore_client():
    """Return Firestore client if GOOGLE_CLOUD_PROJECT is set, else None."""
    global _client
    if _client is not None:
        return _client

    from app.config import settings

    project = (settings.google_cloud_project or "").strip()
    # Treat the unfilled .env.example placeholder as "not configured" so a
    # misconfigured environment falls back to SQLite instead of making doomed
    # Firestore RPCs.
    if not project or project == "your-gcp-project-id":
        return None

    try:
        from google.cloud import firestore

        _client = firestore.Client(
            project=project,
            database=settings.firestore_database_id,
        )
        logger.info(f"Firestore client initialized: project={project}")
        return _client
    except Exception as e:
        logger.warning(f"Firestore client init failed: {e}")
        return None
