import json
import logging
import unicodedata
from typing import Optional

logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("　", "").replace(" ", "").strip().lower()
    return normalized


def _texts_match(a: Optional[str], b: Optional[str]) -> bool:
    if not a or not b:
        return False
    return normalize_text(a) == normalize_text(b)


def _text_contains(haystack: Optional[str], needle: Optional[str]) -> bool:
    if not haystack or not needle:
        return False
    return normalize_text(needle) in normalize_text(haystack)


def match_book_to_sale_item(book, sale_item) -> tuple:
    """
    Returns (is_match, is_certain)
    """
    if book.asin and sale_item.asin:
        if book.asin == sale_item.asin:
            return True, True

    if book.amazon_url and sale_item.amazon_url:
        if book.amazon_url.rstrip("/") == sale_item.amazon_url.rstrip("/"):
            return True, True
        from app.services.scraper import _extract_asin_from_url
        book_asin = _extract_asin_from_url(book.amazon_url)
        item_asin = _extract_asin_from_url(sale_item.amazon_url)
        if book_asin and item_asin and book_asin == item_asin:
            return True, True

    if book.sale_bon_url and sale_item.sale_bon_url:
        if book.sale_bon_url.rstrip("/") == sale_item.sale_bon_url.rstrip("/"):
            return True, True

    if book.title and sale_item.title and book.author and sale_item.author:
        if _texts_match(book.title, sale_item.title) and _texts_match(
            book.author, sale_item.author
        ):
            return True, True

    if book.title and sale_item.title and book.publisher and sale_item.publisher:
        if _texts_match(book.title, sale_item.title) and _texts_match(
            book.publisher, sale_item.publisher
        ):
            return True, True

    if book.title and sale_item.title:
        if _texts_match(book.title, sale_item.title):
            return True, False
        if (_text_contains(book.title, sale_item.title) or
                _text_contains(sale_item.title, book.title)):
            return True, False

    return False, False


def check_volume_match(book, sale_item) -> bool:
    if not book.target_volumes:
        return True

    try:
        target_vols = json.loads(book.target_volumes)
        if not target_vols:
            return True
    except (json.JSONDecodeError, TypeError):
        return True

    if not sale_item.volume:
        return book.series_watch

    sale_vol = normalize_text(sale_item.volume)
    for vol in target_vols:
        if normalize_text(str(vol)) in sale_vol or sale_vol in normalize_text(str(vol)):
            return True

    return book.series_watch


def match_books(sale_items: list, books: list) -> list:
    """
    Returns list of (book, sale_item, is_certain)
    """
    results = []

    for sale_item in sale_items:
        for book in books:
            if not getattr(book, "enabled", True):
                continue

            is_match, is_certain = match_book_to_sale_item(book, sale_item)

            if is_match:
                vol_match = check_volume_match(book, sale_item)
                if not vol_match:
                    continue

                results.append((book, sale_item, is_certain))
                logger.info(
                    "Match: "
                    f"book='{book.title}' <-> sale='{sale_item.title}' "
                    f"(certain={is_certain})"
                )

    return results
