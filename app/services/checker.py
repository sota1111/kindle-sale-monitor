import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.book import Book
from app.models.log import ErrorLog, MonitorLog
from app.models.notification_condition import NotificationCondition
from app.models.sale_history import SaleHistory
from app.models.skip_log import SkipLog
from app.services.condition_evaluator import evaluate_conditions

logger = logging.getLogger(__name__)


def _record_error(
    db: Session, url: Optional[str], error_type: str, error_msg: str, stack: str = ""
) -> None:
    error = ErrorLog(
        occurred_at=datetime.now(timezone.utc),
        url=url,
        error_type=error_type,
        error_message=error_msg,
        stack_trace=stack,
    )
    db.add(error)
    try:
        db.commit()
    except Exception:
        db.rollback()


def _sale_item_to_history_dict(sale_item) -> dict:
    return {
        "volume": sale_item.volume,
        "sale_type": sale_item.sale_type,
        "discount_rate": sale_item.discount_rate,
        "point_rate": sale_item.point_rate,
        "cashback_info": sale_item.cashback_info,
        "price": sale_item.price,
        "effective_price": sale_item.effective_price,
        "is_free": sale_item.is_free,
        "is_cheapest": sale_item.is_cheapest,
        "is_high_return": sale_item.is_high_return,
        "categories": json.dumps(sale_item.categories, ensure_ascii=False),
        "tags": json.dumps(sale_item.tags, ensure_ascii=False),
        "display_text": sale_item.display_text,
        "amazon_url": sale_item.amazon_url,
        "sale_bon_url": sale_item.sale_bon_url,
        "fetched_at": sale_item.fetched_at,
        "notified": False,
    }


def _is_duplicate_sale(db: Session, book_id: int, sale_item) -> bool:
    last_notified = (
        db.query(SaleHistory)
        .filter(
            SaleHistory.book_id == book_id,
            SaleHistory.notified.is_(True),
        )
        .order_by(SaleHistory.fetched_at.desc())
        .first()
    )

    if not last_notified:
        return False

    return (
        last_notified.volume == sale_item.volume
        and last_notified.discount_rate == sale_item.discount_rate
        and last_notified.point_rate == sale_item.point_rate
        and last_notified.cashback_info == sale_item.cashback_info
        and last_notified.is_free == sale_item.is_free
        and last_notified.is_cheapest == sale_item.is_cheapest
        and last_notified.is_high_return == sale_item.is_high_return
        and last_notified.display_text == sale_item.display_text
        and last_notified.sale_bon_url == sale_item.sale_bon_url
    )


def run_check_all(db: Session) -> dict:
    from app.config import settings
    from app.services.matcher import match_books
    from app.services.notifier import send_notification

    started_at = datetime.now(timezone.utc)
    monitor_log = MonitorLog(started_at=started_at, status="running")
    db.add(monitor_log)
    db.commit()
    db.refresh(monitor_log)

    books_checked = 0
    sales_found = 0
    notified_count = 0

    try:
        books = db.query(Book).filter(Book.enabled.is_(True)).all()
        books_checked = len(books)
        logger.info(f"Starting check for {books_checked} books")

        if not books:
            monitor_log.status = "success"
            monitor_log.finished_at = datetime.now(timezone.utc)
            monitor_log.books_checked = 0
            db.commit()
            return {"books_checked": 0, "sales_found": 0, "notified": 0}

        try:
            from app.models.settings import AppSettings

            interval_setting = (
                db.query(AppSettings)
                .filter(AppSettings.key == "request_interval_seconds")
                .first()
            )
            interval = (
                int(interval_setting.value)
                if interval_setting and interval_setting.value
                else settings.request_interval_seconds
            )

            retry_setting = db.query(AppSettings).filter(AppSettings.key == "max_retries").first()
            max_retries = (
                int(retry_setting.value)
                if retry_setting and retry_setting.value
                else settings.max_retries
            )

            from app.services.scraper import scrape_sale_bon_with_diagnostics

            sale_items, diagnostics = scrape_sale_bon_with_diagnostics(
                books=books,
                interval_seconds=interval,
                max_retries=max_retries,
                timeout=settings.request_timeout_seconds,
            )

            if diagnostics.failures:
                from app.services.notifier import send_scrape_failure_notification

                failure_info = []
                for outcome in diagnostics.failures:
                    category_name = (
                        outcome.failure_category.value
                        if outcome.failure_category
                        else "UNEXPECTED"
                    )
                    _record_error(
                        db,
                        outcome.url,
                        error_type=category_name,
                        error_msg=outcome.detail or "Unknown error",
                    )
                    failure_info.append(
                        (category_name, outcome.url, outcome.detail or "Unknown error")
                    )

                send_scrape_failure_notification(failure_info, db=db)

                if len(diagnostics.failures) == len(diagnostics.outcomes) and not sale_items:
                    monitor_log.status = "failed"
                    monitor_log.error_message = "All scraping pages failed"
                    monitor_log.finished_at = datetime.now(timezone.utc)
                    db.commit()
                    return {
                        "books_checked": books_checked,
                        "sales_found": 0,
                        "notified": 0,
                        "error": "All scraping pages failed",
                    }

        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            _record_error(db, None, "ScrapingError", str(e), traceback.format_exc())
            monitor_log.status = "failed"
            monitor_log.error_message = str(e)
            monitor_log.finished_at = datetime.now(timezone.utc)
            db.commit()
            return {
                "books_checked": books_checked,
                "sales_found": 0,
                "notified": 0,
                "error": str(e),
            }

        matches = match_books(sale_items, books)

        for book, sale_item, is_certain in matches:
            try:
                history_data = _sale_item_to_history_dict(sale_item)
                history_data["book_id"] = book.id
                sale_history = SaleHistory(**history_data)
                db.add(sale_history)
                db.flush()
                sales_found += 1

                if not is_certain:
                    logger.info(f"Uncertain match for '{book.title}', skipping notification")
                    continue

                if _is_duplicate_sale(db, book.id, sale_item):
                    logger.info(f"Duplicate sale for '{book.title}', skipping notification")
                    continue

                conditions = (
                    db.query(NotificationCondition)
                    .filter(NotificationCondition.book_id == book.id)
                    .all()
                )
                result = evaluate_conditions(book, sale_item, conditions)

                if result.should_notify:
                    reason = " / ".join(result.matched_reasons)
                    success = send_notification(
                        book, sale_history, reason, db, matched_reasons=result.matched_reasons
                    )
                    if success:
                        sale_history.notified = True
                        notified_count += 1
                else:
                    skip_log = SkipLog(
                        book_id=book.id,
                        sale_history_id=sale_history.id,
                        skip_reason=" / ".join(result.skip_reasons),
                    )
                    db.add(skip_log)
                    logger.info(
                        f"Skipped notification for '{book.title}': "
                        f"{' / '.join(result.skip_reasons)}"
                    )

            except Exception as e:
                logger.error(f"Error processing match for book {book.id}: {e}")
                _record_error(
                    db,
                    getattr(sale_item, "sale_bon_url", None),
                    "MatchProcessingError",
                    str(e),
                    traceback.format_exc(),
                )

        db.commit()

        monitor_log.status = "success"
        monitor_log.books_checked = books_checked
        monitor_log.sales_found = sales_found
        monitor_log.notified = notified_count
        monitor_log.finished_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            "Check complete: "
            f"{books_checked} books, {sales_found} sales, {notified_count} notifications"
        )
        return {
            "books_checked": books_checked,
            "sales_found": sales_found,
            "notified": notified_count,
        }

    except Exception as e:
        logger.error(f"Unexpected error in run_check_all: {e}")
        monitor_log.status = "failed"
        monitor_log.error_message = str(e)
        monitor_log.finished_at = datetime.now(timezone.utc)
        try:
            db.commit()
        except Exception:
            db.rollback()
        raise
