import logging

logger = logging.getLogger(__name__)


def send_notification(book, sale_history, reason: str) -> bool:
    """Stub: Will be implemented in SOT-288."""
    logger.info(f"send_notification called for book_id={getattr(book, 'id', None)} (stub)")
    return False
