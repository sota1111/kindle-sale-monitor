from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.book import Book
from app.models.sale_history import SaleHistory
from app.schemas.dashboard import DashboardSummary, PriceTrendPoint, PriceTrendSeries

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def build_summary(db: Session) -> DashboardSummary:
    """Aggregate dashboard KPIs over all books / sale-history rows.

    Tolerates an empty database (returns zeros), never raises.
    """
    book_count = db.query(Book).count()
    sale_record_count = db.query(SaleHistory).count()
    books_with_history = db.query(SaleHistory.book_id).distinct().count()
    all_time_low_hits = (
        db.query(SaleHistory).filter(SaleHistory.is_cheapest.is_(True)).count()
    )

    avg_discount = (
        db.query(func.avg(SaleHistory.discount_rate))
        .filter(SaleHistory.discount_rate.isnot(None), SaleHistory.discount_rate > 0)
        .scalar()
    )
    avg_discount_rate = round(float(avg_discount), 1) if avg_discount is not None else 0.0

    # "On sale now": books whose most-recent sale-history row is discounted.
    latest_per_book = (
        db.query(
            SaleHistory.book_id.label("book_id"),
            func.max(SaleHistory.fetched_at).label("latest"),
        )
        .group_by(SaleHistory.book_id)
        .subquery()
    )
    on_sale_now = (
        db.query(SaleHistory)
        .join(
            latest_per_book,
            (SaleHistory.book_id == latest_per_book.c.book_id)
            & (SaleHistory.fetched_at == latest_per_book.c.latest),
        )
        .filter(
            (SaleHistory.discount_rate.isnot(None) & (SaleHistory.discount_rate > 0))
            | SaleHistory.is_cheapest.is_(True)
        )
        .count()
    )

    return DashboardSummary(
        book_count=book_count,
        sale_record_count=sale_record_count,
        books_with_history=books_with_history,
        on_sale_now=on_sale_now,
        all_time_low_hits=all_time_low_hits,
        avg_discount_rate=avg_discount_rate,
    )


@router.get("/summary", response_model=DashboardSummary)
def get_summary(db: Session = Depends(get_db)):
    return build_summary(db)


@router.get("/price-trends", response_model=list[PriceTrendSeries])
def get_price_trends(limit: int = 5, db: Session = Depends(get_db)):
    """Return per-book price-trend series for the books with the most history."""
    limit = max(1, min(limit, 20))
    ranked = (
        db.query(SaleHistory.book_id, func.count(SaleHistory.id).label("n"))
        .group_by(SaleHistory.book_id)
        .order_by(func.count(SaleHistory.id).desc())
        .limit(limit)
        .all()
    )

    series: list[PriceTrendSeries] = []
    for book_id, _ in ranked:
        book = db.query(Book).filter(Book.id == book_id).first()
        if book is None:
            continue
        rows = (
            db.query(SaleHistory)
            .filter(SaleHistory.book_id == book_id)
            .order_by(SaleHistory.fetched_at.asc())
            .all()
        )
        points = [
            PriceTrendPoint(
                fetched_at=r.fetched_at,
                price=r.price,
                effective_price=r.effective_price,
            )
            for r in rows
        ]
        series.append(PriceTrendSeries(book_id=book_id, title=book.title, points=points))
    return series
