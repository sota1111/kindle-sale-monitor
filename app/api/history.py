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


@router.get("/api/monitor-logs", response_model=list[MonitorLogResponse])
def list_monitor_logs(limit: int = 100, db: Session = Depends(get_db)):
    return db.query(MonitorLog).order_by(MonitorLog.started_at.desc()).limit(limit).all()


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
