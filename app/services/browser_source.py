"""Logged-in local browser data source (Playwright, persistent profile).

Drives a **local** Chromium via Playwright using a persistent profile
(``launch_persistent_context``) so an already-logged-in Amazon session is reused.
For each wishlist ASIN it visits ``https://www.amazon.co.jp/dp/<asin>`` and reads the
Kindle price / points / discount / free status into the existing :class:`SaleItem`
dataclass, so the matcher / checker / notifier pipeline is reused unchanged.

Design notes
------------
* This source is **opt-in only** (``DATA_SOURCE=browser``); ``auto`` never selects it.
* The first login is performed manually by the operator with a one-off headed run
  (``BROWSER_HEADLESS=false``); steady-state runs are headless and reuse the saved
  profile cookies under ``BROWSER_PROFILE_DIR``.
* Steady-state running on Cloud Run is NOT supported (headed first-login + a desktop
  profile are local-only). This is a local-PC data source by design.
* Like the scraper / PA-API client this NEVER raises out of a fetch: every failure
  becomes a :class:`PageOutcome` recorded in the diagnostics.

The Playwright *sync* API cannot run inside a thread that already owns a running
asyncio event loop, so the whole browser session is executed on a dedicated worker
thread (which has no loop), making it safe whether or not the caller is async.
"""

import logging
import os
import threading
import time
from typing import Any, Callable, Optional

from app.services.paapi_client import _collect_asins
from app.services.scraper import (
    PageOutcome,
    SaleItem,
    ScrapeDiagnostics,
    ScrapeFailureCategory,
    _parse_price,
    _parse_rate,
)

logger = logging.getLogger(__name__)

AMAZON_DP_BASE = "https://www.amazon.co.jp/dp/"


def _parse_points(text: Optional[str]) -> Optional[int]:
    """Parse a loyalty-point count like ``"500ポイント"`` / ``"獲得ポイント: 50pt"``."""
    if not text:
        return None
    import re

    match = re.search(r"(\d[\d,]*)\s*(?:ポイント|pt|ポイント還元|point)", text, re.IGNORECASE)
    if not match:
        # Fall back to the first integer in the string.
        match = re.search(r"(\d[\d,]*)", text)
    if not match:
        return None
    digits = match.group(1).replace(",", "")
    return int(digits) if digits else None


def _build_sale_item(asin: str, url: str, fields: dict[str, Any]) -> Optional[SaleItem]:
    """Build a :class:`SaleItem` from raw strings scraped off a ``/dp/<asin>`` page.

    ``fields`` keys (all optional, values are raw page text or ``None``):
    ``title``, ``price_text``, ``points_text``, ``list_price_text``, ``discount_text``.
    Returns ``None`` when neither a title nor a price could be read (caller treats this
    as a suspected structure change). Pure / side-effect free so it is unit-testable.
    """
    title = (fields.get("title") or "").strip()
    price = _parse_price(fields.get("price_text") or "")

    if not title and price is None:
        return None

    sale = SaleItem(title=title or asin)
    sale.asin = asin
    sale.amazon_url = url
    sale.price = price

    if price is not None:
        sale.is_free = price == 0

        # Discount: explicit percentage, else derive from a list/reference price.
        discount = _parse_rate(fields.get("discount_text") or "")
        if discount is None:
            list_price = _parse_price(fields.get("list_price_text") or "")
            if list_price and price and list_price > price:
                discount = int(round((list_price - price) / list_price * 100))
        sale.discount_rate = discount

        # Loyalty points → point rate and effective price.
        points = _parse_points(fields.get("points_text"))
        if points and price > 0:
            sale.point_rate = int(round(points / price * 100))
            sale.effective_price = price - points
        else:
            sale.effective_price = price

    # sale_type / display_text precedence mirrors paapi_client._parse_item.
    if sale.is_free:
        sale.sale_type = "無料"
    elif sale.discount_rate:
        sale.sale_type = f"{sale.discount_rate}%OFF"
    elif sale.point_rate:
        sale.sale_type = f"ポイント{sale.point_rate}%還元"
    sale.display_text = sale.sale_type

    return sale


def _first_text(page: Any, selectors: list[str]) -> Optional[str]:
    """Return the trimmed text of the first matching, visible selector (best effort)."""
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            text = locator.inner_text(timeout=1500)
            if text and text.strip():
                return text.strip()
        except Exception:  # noqa: BLE001 - selector misses must never raise
            continue
    return None


def _extract_fields_from_page(page: Any) -> dict[str, Any]:
    """Pull the raw price/points/title strings off a loaded ``/dp`` page (best effort)."""
    return {
        "title": _first_text(page, ["#productTitle", "#ebooksProductTitle", "title"]),
        "price_text": _first_text(
            page,
            [
                "#kindle-price",
                "#tmm-grid-swatch-KINDLE .a-color-price",
                "#tmmSwatches .a-color-price",
                "span.a-price span.a-offscreen",
                "#price",
            ],
        ),
        "points_text": _first_text(
            page,
            [
                "#Ebooks-desktop-KINDLE-prices .loyalty-points",
                ".loyalty-points",
                "#points",
                "[data-feature-name='loyaltyPoints']",
            ],
        ),
        "list_price_text": _first_text(
            page,
            [
                "span.a-price.a-text-price span.a-offscreen",
                "#listPrice",
                ".a-text-strike",
            ],
        ),
        "discount_text": _first_text(
            page,
            [
                "#dp_savings_percentage",
                ".savingsPercentage",
                "[class*='savingsPercentage']",
            ],
        ),
    }


def _categorize(exc: BaseException) -> tuple[ScrapeFailureCategory, str]:
    """Map a Playwright/runtime exception to a diagnostics failure category."""
    name = type(exc).__name__
    detail = str(exc) or name
    if "Timeout" in name:
        return ScrapeFailureCategory.TIMEOUT, detail
    lowered = detail.lower()
    if any(t in lowered for t in ("net::", "connection", "dns", "socket")):
        return ScrapeFailureCategory.NETWORK, detail
    return ScrapeFailureCategory.UNEXPECTED, detail


def _run_browser_session(
    asins: list[str],
    *,
    profile_dir: str,
    headless: bool,
    interval_seconds: int,
    max_retries: int,
    timeout: int,
    extract: Callable[[Any], dict[str, Any]] = _extract_fields_from_page,
) -> tuple[list[SaleItem], ScrapeDiagnostics]:
    """Open one persistent Chromium context and visit each ``/dp/<asin>`` page.

    Runs the Playwright *sync* API; must be called from a thread without a running
    asyncio loop. Never raises — launch/import failures are turned into diagnostics.
    """
    diagnostics = ScrapeDiagnostics()
    all_items: list[SaleItem] = []

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001 - missing dependency must not crash the app
        logger.warning("Playwright is not installed: %s", exc)
        diagnostics.outcomes.append(
            PageOutcome(
                url=AMAZON_DP_BASE,
                ok=False,
                failure_category=ScrapeFailureCategory.UNEXPECTED,
                detail=(
                    "Playwright not available. Install with: "
                    "uv add playwright && uv run playwright install chromium"
                ),
            )
        )
        return all_items, diagnostics

    expanded_profile = os.path.expanduser(profile_dir)
    os.makedirs(expanded_profile, exist_ok=True)

    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                user_data_dir=expanded_profile,
                headless=headless,
            )
            try:
                page = context.new_page()
                for asin in asins:
                    url = f"{AMAZON_DP_BASE}{asin}"
                    items, outcome = _visit_asin(
                        page,
                        url=url,
                        asin=asin,
                        interval_seconds=interval_seconds,
                        max_retries=max_retries,
                        timeout=timeout,
                        extract=extract,
                    )
                    diagnostics.outcomes.append(outcome)
                    all_items.extend(items)
                    # Polite, human-like pacing between product pages.
                    time.sleep(interval_seconds)
            finally:
                context.close()
    except Exception as exc:  # noqa: BLE001 - launch failures recorded, never raised
        category, detail = _categorize(exc)
        logger.warning("Browser session failed: %s", detail)
        diagnostics.outcomes.append(
            PageOutcome(
                url=AMAZON_DP_BASE,
                ok=False,
                failure_category=category,
                detail=f"browser launch/session error: {detail}",
            )
        )

    return all_items, diagnostics


def _visit_asin(
    page: Any,
    *,
    url: str,
    asin: str,
    interval_seconds: int,
    max_retries: int,
    timeout: int,
    extract: Callable[[Any], dict[str, Any]],
) -> tuple[list[SaleItem], PageOutcome]:
    """Navigate to one ``/dp`` page (with retries) and parse a single SaleItem."""
    outcome = PageOutcome(url=url, ok=False)
    last_exc: Optional[BaseException] = None

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                wait_time = interval_seconds * (2 ** (attempt - 1))
                logger.info("Retry %s for %s, waiting %ss", attempt, url, wait_time)
                time.sleep(wait_time)

            page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            fields = extract(page)
            item = _build_sale_item(asin, url, fields)

            if item is None:
                outcome.ok = False
                outcome.failure_category = ScrapeFailureCategory.STRUCTURE_CHANGE
                outcome.detail = "page loaded but no title/price parsed"
                logger.warning("No price parsed for %s - possible structure change", url)
                return [], outcome

            outcome.ok = True
            outcome.items_count = 1
            logger.info("Browser fetched %s (%s)", asin, item.sale_type or "no sale")
            return [item], outcome
        except Exception as exc:  # noqa: BLE001 - retried; categorized below
            last_exc = exc
            logger.warning("Error fetching %s: %s (attempt %s)", url, exc, attempt + 1)

    if last_exc is not None:
        outcome.failure_category, outcome.detail = _categorize(last_exc)
    logger.error("Failed to fetch %s after %s retries", url, max_retries)
    return [], outcome


def fetch_browser_with_diagnostics(
    books: Optional[list[Any]] = None,
    interval_seconds: int = 2,
    max_retries: int = 3,
    timeout: int = 30,
) -> tuple[list[SaleItem], ScrapeDiagnostics]:
    """Fetch current Kindle offers by driving a logged-in local browser.

    Mirrors :func:`app.services.scraper.scrape_sale_bon_async` /
    :func:`app.services.paapi_client.fetch_paapi_with_diagnostics`'s return shape so the
    checker can swap data sources without further changes. Never raises.
    """
    from app.config import settings

    asins = _collect_asins(books)
    if not asins:
        logger.info("Browser source: no resolvable ASINs in wishlist; nothing to fetch")
        return [], ScrapeDiagnostics()

    profile_dir = getattr(settings, "browser_profile_dir", "~/.kindle-monitor/browser-profile")
    headless = bool(getattr(settings, "browser_headless", True))

    result: dict[str, tuple[list[SaleItem], ScrapeDiagnostics]] = {}

    def runner() -> None:
        result["v"] = _run_browser_session(
            asins,
            profile_dir=profile_dir,
            headless=headless,
            interval_seconds=interval_seconds,
            max_retries=max_retries,
            timeout=timeout,
        )

    # Always run on a dedicated thread: Playwright's sync API refuses to start inside a
    # thread that owns a running asyncio loop, and a fresh thread never has one.
    thread = threading.Thread(target=runner, name="browser-source")
    thread.start()
    thread.join()

    items, diagnostics = result.get("v", ([], ScrapeDiagnostics()))
    logger.info("Browser source total items: %s", len(items))
    return items, diagnostics
