"""Data-source dispatcher.

Selects between the Amazon PA-API 5.0 client (the real data source), the legacy
sale-bon.com scraper, and a logged-in local browser (Playwright) source based on
``settings.data_source`` and whether PA-API credentials are configured. All back-ends
return the same ``(list[SaleItem], ScrapeDiagnostics)`` shape so the checker is agnostic
to the source. ``browser`` is opt-in only (``DATA_SOURCE=browser``); ``auto`` never
selects it.
"""

import logging
from typing import Any, Optional

from app.services.scraper import SaleItem, ScrapeDiagnostics

logger = logging.getLogger(__name__)


def _resolve_source(settings: Any) -> str:
    from app.services.paapi_client import paapi_configured

    choice = (getattr(settings, "data_source", "auto") or "auto").lower()
    if choice == "paapi":
        return "paapi"
    if choice == "scrape":
        return "scrape"
    if choice == "browser":
        return "browser"
    # auto (browser is opt-in only and never selected here)
    return "paapi" if paapi_configured(settings) else "scrape"


def fetch_sale_items_with_diagnostics(
    books: Optional[list[Any]] = None,
    interval_seconds: int = 2,
    max_retries: int = 3,
    timeout: int = 30,
) -> tuple[list[SaleItem], ScrapeDiagnostics]:
    from app.config import settings

    source = _resolve_source(settings)
    logger.info("Data source selected: %s", source)

    if source == "paapi":
        from app.services.paapi_client import fetch_paapi_with_diagnostics

        return fetch_paapi_with_diagnostics(
            books=books,
            interval_seconds=interval_seconds,
            max_retries=max_retries,
            timeout=timeout,
        )

    if source == "browser":
        from app.services.browser_source import fetch_browser_with_diagnostics

        return fetch_browser_with_diagnostics(
            books=books,
            interval_seconds=interval_seconds,
            max_retries=max_retries,
            timeout=timeout,
        )

    from app.services.scraper import scrape_sale_bon_with_diagnostics

    return scrape_sale_bon_with_diagnostics(
        books=books,
        interval_seconds=interval_seconds,
        max_retries=max_retries,
        timeout=timeout,
    )
