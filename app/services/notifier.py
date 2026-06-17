import json
import logging

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def send_notification(
    book, sale_history, reason: str, db: Session, matched_reasons: list[str] | None = None
) -> bool:
    """Send Discord notification for a sale. Returns True on success."""
    from datetime import datetime, timezone

    from app.config import settings
    from app.models.notification import NotificationHistory

    matched_json = json.dumps(matched_reasons, ensure_ascii=False) if matched_reasons else None
    notif_record = NotificationHistory(
        book_id=book.id,
        sale_history_id=sale_history.id,
        reason=reason,
        matched_conditions=matched_json,
        notified_at=datetime.now(timezone.utc),
    )

    if not settings.discord_webhook_url:
        logger.warning("DISCORD_WEBHOOK_URL not set, skipping notification")
        notif_record.success = False
        notif_record.error_message = "DISCORD_WEBHOOK_URL not configured"
        db.add(notif_record)
        db.commit()
        return False

    conditions_text = ""
    if matched_reasons:
        conditions_text = "\n".join(f"  ・{r}" for r in matched_reasons)
    else:
        conditions_text = f"  ・{reason}"

    message = f"""【Kindle セール通知】
通知理由: {reason}
作品名: {book.title}
対象巻: {sale_history.volume or "全巻"}
セール種別: {sale_history.sale_type or "不明"}
割引率: {sale_history.discount_rate or 0}%
ポイント還元率: {sale_history.point_rate or 0}%
過去最安値更新: {"✅ 更新" if sale_history.is_cheapest else "❌ 非更新"}
キャッシュバック: {sale_history.cashback_info or "なし"}
条件マッチ理由:
{conditions_text}
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


def send_scrape_failure_notification(
    failures: list[tuple[str, str, str]], db: Session | None = None
) -> bool:
    """Send summary of scraping failures to Discord. Returns True on success."""
    from app.config import settings

    if not settings.discord_webhook_url:
        logger.warning("DISCORD_WEBHOOK_URL not set, skipping failure notification")
        return False

    if not failures:
        return True

    failure_lines = []
    for category, url, detail in failures:
        action = ""
        if category == "STRUCTURE_CHANGE":
            action = "推奨アクション: sale-bon のHTML構造変更の可能性。セレクタ確認をしてください。"
        elif category == "HTTP_ERROR":
            action = "推奨アクション: 対象URLの有効性またはレート制限を確認してください。"
        elif category in ("TIMEOUT", "NETWORK"):
            action = "推奨アクション: ネットワーク接続と対象サイトの稼働状況を確認してください。"
        else:
            action = "推奨アクション: ログを確認し、予期しないエラーの原因を調査してください。"

        failure_lines.append(f"・分類: {category}\n  URL: {url}\n  詳細: {detail}\n  {action}")

    failure_details = "\n".join(failure_lines)

    message = f"""【Kindle セールモニター スクレイピング失敗通知】
一部またはすべてのページのスクレイピングに失敗しました。

{failure_details}

※ 同一実行内の失敗をまとめて通知しています。"""

    try:
        import httpx

        resp = httpx.post(
            settings.discord_webhook_url,
            json={"content": message},
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Scraping failure notification sent")
        return True
    except Exception as e:
        logger.error(f"Failed to send failure notification: {e}")
        return False
