import json
import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

from app.models.book import Book
from app.services.matcher import normalize_text

logger = logging.getLogger(__name__)

# Columns that may appear in a wishlist entry and map directly to Book.
_ALLOWED_FIELDS = {
    "title",
    "author",
    "publisher",
    "amazon_url",
    "asin",
    "sale_bon_url",
    "target_volumes",
    "series_watch",
    "note",
    "enabled",
}


def _existing_by_asin(db: Session, asin: Optional[str]) -> Optional[Book]:
    if not asin:
        return None
    return db.query(Book).filter(Book.asin == asin).first()


def _existing_by_title_author(db: Session, title: str, author: Optional[str]) -> Optional[Book]:
    norm_title = normalize_text(title)
    norm_author = normalize_text(author or "")
    for book in db.query(Book).all():
        if normalize_text(book.title or "") == norm_title and (
            normalize_text(book.author or "") == norm_author
        ):
            return book
    return None


def seed_books_from_wishlist(db: Session, wishlist_path: str) -> int:
    """Idempotently insert books from a wishlist JSON file.

    Each entry is inserted only if no Book with the same ASIN exists and no Book
    with the same normalized (title + author) exists. Existing books are never
    modified or deleted. Returns the number of books inserted.
    """
    if not wishlist_path or not os.path.exists(wishlist_path):
        logger.info("Wishlist file not found, skipping seed: %s", wishlist_path)
        return 0

    try:
        with open(wishlist_path, encoding="utf-8") as f:
            entries = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Failed to read wishlist file %s: %s", wishlist_path, e)
        return 0

    if not isinstance(entries, list):
        logger.error("Wishlist file %s is not a JSON array", wishlist_path)
        return 0

    inserted = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        title = entry.get("title")
        if not title:
            continue

        if _existing_by_asin(db, entry.get("asin")):
            continue
        if _existing_by_title_author(db, title, entry.get("author")):
            continue

        data = {k: v for k, v in entry.items() if k in _ALLOWED_FIELDS}
        db.add(Book(**data))
        inserted += 1

    if inserted:
        db.commit()
        logger.info("Seeded %d book(s) from %s", inserted, wishlist_path)
    else:
        logger.info("No new books to seed from %s", wishlist_path)
    return inserted
