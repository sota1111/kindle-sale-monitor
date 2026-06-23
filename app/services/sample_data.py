"""Provisional (sample) price-history data seeding.

This module registers *provisional* sample data so the dashboard can be evaluated
without a live data source. It assumes data could be collected locally and instead
synthesises a realistic ~90-day price-trend series for a handful of books.

Every generated row is tagged with ``sale_type == SAMPLE_SALE_TYPE`` so it can be
identified and regenerated independently of real data. Real (non-sample) rows are
never modified or deleted.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.book import Book
from app.models.sale_history import SaleHistory
from app.services.matcher import normalize_text

logger = logging.getLogger(__name__)

# Marker that identifies provisional rows created by this seeder.
SAMPLE_SALE_TYPE = "sample"

# Number of daily price-trend points generated per book.
SAMPLE_DAYS = 90

# Sample books and their base (list) price in yen. Existing books with a matching
# normalized title are reused; missing ones are inserted.
_SAMPLE_BOOKS: list[dict] = [
    {"title": "BLUE GIANT", "author": "石塚真一", "base_price": 715},
    {"title": "クロサギ", "author": "黒丸 / 夏原武", "base_price": 660},
    {"title": "HUNTER×HUNTER モノクロ版", "author": "冨樫義博", "base_price": 502},
    {"title": "鋼の錬金術師", "author": "荒川弘", "base_price": 460},
    {"title": "BECK", "author": "ハロルド作石", "base_price": 700},
]

# Day offsets (from the start of the window) where a sale dip occurs, with the
# discount rate and point rate applied. Deterministic so tests are stable.
_SALE_EVENTS: list[dict] = [
    {"start": 18, "length": 5, "discount_rate": 20, "point_rate": 0},
    {"start": 41, "length": 4, "discount_rate": 30, "point_rate": 10},
    {"start": 67, "length": 6, "discount_rate": 50, "point_rate": 20},
]


def _find_existing_book(db: Session, title: str, author: str | None) -> Book | None:
    norm_title = normalize_text(title)
    norm_author = normalize_text(author or "")
    for book in db.query(Book).all():
        if normalize_text(book.title or "") == norm_title and (
            normalize_text(book.author or "") == norm_author
        ):
            return book
    return None


def _event_for_day(day: int) -> dict | None:
    for event in _SALE_EVENTS:
        if event["start"] <= day < event["start"] + event["length"]:
            return event
    return None


def _build_history_rows(book_id: int, base_price: int, now: datetime) -> list[SaleHistory]:
    """Build a deterministic ~SAMPLE_DAYS daily price-trend series for one book.

    The list price stays at ``base_price`` except during predefined sale windows,
    where the effective price drops by the event's discount rate. The single
    cheapest point is flagged ``is_cheapest``.
    """
    start = now - timedelta(days=SAMPLE_DAYS - 1)
    rows: list[SaleHistory] = []
    prices: list[int] = []

    for day in range(SAMPLE_DAYS):
        fetched_at = start + timedelta(days=day)
        event = _event_for_day(day)
        if event:
            discount_rate = int(event["discount_rate"])
            point_rate = int(event["point_rate"])
            price = base_price
            effective_price = round(base_price * (100 - discount_rate) / 100)
        else:
            discount_rate = 0
            point_rate = 0
            price = base_price
            effective_price = base_price
        prices.append(effective_price)
        rows.append(
            SaleHistory(
                book_id=book_id,
                volume="1",
                sale_type=SAMPLE_SALE_TYPE,
                discount_rate=discount_rate,
                point_rate=point_rate,
                price=price,
                effective_price=effective_price,
                is_free=False,
                is_cheapest=False,
                is_high_return=point_rate >= 20,
                fetched_at=fetched_at,
                notified=False,
            )
        )

    # Flag the (first) lowest effective-price point as the all-time low.
    lowest = min(prices)
    for row, eff in zip(rows, prices):
        if eff == lowest:
            row.is_cheapest = True
            break
    return rows


def _delete_sample_rows(db: Session, book_id: int) -> None:
    db.query(SaleHistory).filter(
        SaleHistory.book_id == book_id,
        SaleHistory.sale_type == SAMPLE_SALE_TYPE,
    ).delete(synchronize_session=False)


def seed_sample_data(db: Session, *, force: bool = False) -> dict:
    """Idempotently register provisional sample price-history data.

    For each entry in ``_SAMPLE_BOOKS`` an existing book is reused (matched by
    normalized title + author) or inserted, then a deterministic price-trend
    series tagged ``sale_type="sample"`` is generated.

    Idempotency: a book that already has sample rows is skipped unless
    ``force=True``, in which case its existing sample rows are deleted and
    regenerated. Non-sample rows are never touched.

    Returns ``{"books": <int>, "sale_history_rows": <int>}``.
    """
    now = datetime.utcnow()
    books_seeded = 0
    rows_inserted = 0

    for entry in _SAMPLE_BOOKS:
        title = entry["title"]
        author = entry.get("author")
        base_price = int(entry["base_price"])

        book = _find_existing_book(db, title, author)
        if book is None:
            book = Book(title=title, author=author, note="サンプルデータ")
            db.add(book)
            db.flush()  # assign book.id

        existing_samples = (
            db.query(SaleHistory)
            .filter(
                SaleHistory.book_id == book.id,
                SaleHistory.sale_type == SAMPLE_SALE_TYPE,
            )
            .count()
        )
        if existing_samples and not force:
            continue
        if existing_samples and force:
            _delete_sample_rows(db, book.id)

        rows = _build_history_rows(book.id, base_price, now)
        db.add_all(rows)
        books_seeded += 1
        rows_inserted += len(rows)

    if books_seeded:
        db.commit()
        logger.info(
            "Seeded sample data: %d book(s), %d price-history row(s)",
            books_seeded,
            rows_inserted,
        )
    else:
        logger.info("Sample data already present; nothing to seed (use force=True to regenerate)")

    return {"books": books_seeded, "sale_history_rows": rows_inserted}
