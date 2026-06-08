import logging

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def run_check_all(db: Session) -> None:
    """Stub: Full check implementation will be added in SOT-287."""
    logger.info("run_check_all called (stub)")
