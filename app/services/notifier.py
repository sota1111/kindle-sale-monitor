import logging
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def send_notification(book, sale_history, reason: str, db: Session) -> bool:
    """Send Discord notification for a sale. Returns True on success."""
    from app.config import settings
    from app.models.notification import NotificationHistory
    from datetime import datetime, timezone

    notif_record = NotificationHistory(
        book_id=book.id,
        sale_history_id=sale_history.id,
        reason=reason,
        notified_at=datetime.now(timezone.utc),
    )

    if not settings.discord_webhook_url:
        logger.warning("DISCORD_WEBHOOK_URL not set, skipping notification")
        notif_record.success = False
        notif_record.error_message = "DISCORD_WEBHOOK_URL not configured"
        db.add(notif_record)
        db.commit()
        return False

    message = f"""【Kindle セール通知】
通知理由: {reason}
作品名: {book.title}
対象巻: {sale_history.volume or "全巻"}
セール種別: {sale_history.sale_type or "不明"}
割引率: {sale_history.discount_rate or 0}%
ポイント還元率: {sale_history.point_rate or 0}%
キャッシュバック: {sale_history.cashback_info or "なし"}
価格: {sale_history.price or "不明"}円
実質価格: {sale_history.effective_price or "不明"}円
sale-bon表示: {sale_history.display_text or ""}
Amazon: {sale_history.amazon_url or ""}
sale-bon: {sale_history.sale_bon_url or ""}
取得日時: {sale_history.fetched_at}

⚠️ 購入前にAmazon側の価格・ポイント還元率を確認してください。"""

    try:
        import httpx
        resp = httpx.post(
            settings.discord_webhook_url,
            json={"content": message},
            timeout=10,
        )
        resp.raise_for_status()
        notif_record.success = True
        db.add(notif_record)
        db.commit()
        logger.info(f"Notification sent for book: {book.title}")
        return True
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
        notif_record.success = False
        notif_record.error_message = str(e)
        db.add(notif_record)
        db.commit()
        return False
