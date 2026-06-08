from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.notification import NotificationHistory
from app.models.sale_history import SaleHistory
from app.schemas.notification import NotificationHistoryResponse
from app.schemas.sale_history import SaleHistoryResponse

router = APIRouter(tags=["history"])


@router.get("/api/sales", response_model=list[SaleHistoryResponse])
def list_sales(limit: int = 100, db: Session = Depends(get_db)):
    return db.query(SaleHistory).order_by(SaleHistory.fetched_at.desc()).limit(limit).all()


@router.get("/api/notifications", response_model=list[NotificationHistoryResponse])
def list_notifications(limit: int = 100, db: Session = Depends(get_db)):
    return (
        db.query(NotificationHistory)
        .order_by(NotificationHistory.notified_at.desc())
        .limit(limit)
        .all()
    )
