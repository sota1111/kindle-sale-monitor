from types import SimpleNamespace

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.log import MonitorLog
from app.models.notification import NotificationHistory
from app.models.sale_history import SaleHistory
from app.schemas.log import MonitorLogResponse
from app.schemas.notification import NotificationHistoryResponse
from app.schemas.sale_history import PriceHistoryPoint, SaleHistoryResponse

router = APIRouter(tags=["history"])


def _row_to_log(row: dict, idx: int) -> SimpleNamespace:
    """Adapt a Firestore monitor_logs dict to the attribute shape used by the
    template and the MonitorLogResponse schema."""
    return SimpleNamespace(
        id=row.get("id", idx),
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
        books_checked=row.get("books_checked", 0),
        sales_found=row.get("sales_found", 0),
        notified=row.get("notified", 0),
        status=row.get("status"),
        error_message=row.get("error_message"),
    )


def get_recent_monitor_logs(db: Session, limit: int = 100) -> list:
    """Return recent monitor logs, preferring durable Firestore storage.

    On Cloud Run the SQLite DB is ephemeral, so Firestore is the source of
    truth when configured. Falls back to SQLite when Firestore is unavailable
    or empty.
    """
    from app.services.firestore_repository import list_monitor_logs as _fs_list

    fs_logs = _fs_list(limit)
    if fs_logs:
        return [_row_to_log(row, idx) for idx, row in enumerate(fs_logs)]
    return db.query(MonitorLog).order_by(MonitorLog.started_at.desc()).limit(limit).all()


@router.get("/api/monitor-logs", response_model=list[MonitorLogResponse])
def list_monitor_logs(limit: int = 100, db: Session = Depends(get_db)):
    return get_recent_monitor_logs(db, limit)


@router.get("/api/sales", response_model=list[SaleHistoryResponse])
def list_sales(limit: int = 100, db: Session = Depends(get_db)):
    return db.query(SaleHistory).order_by(SaleHistory.fetched_at.desc()).limit(limit).all()


@router.get("/api/books/{book_id}/price-history", response_model=list[PriceHistoryPoint])
def get_price_history(book_id: int, limit: int = 365, db: Session = Depends(get_db)):
    return (
        db.query(SaleHistory)
        .filter(SaleHistory.book_id == book_id)
        .order_by(SaleHistory.fetched_at.asc())
        .limit(limit)
        .all()
    )


@router.get("/api/notifications", response_model=list[NotificationHistoryResponse])
def list_notifications(limit: int = 100, db: Session = Depends(get_db)):
    return (
        db.query(NotificationHistory)
        .order_by(NotificationHistory.notified_at.desc())
        .limit(limit)
        .all()
    )
