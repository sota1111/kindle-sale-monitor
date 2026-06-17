import asyncio
import logging
import threading
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, cast

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag

logger = logging.getLogger(__name__)


class ScrapeFailureCategory(Enum):
    STRUCTURE_CHANGE = "STRUCTURE_CHANGE"
    HTTP_ERROR = "HTTP_ERROR"
    TIMEOUT = "TIMEOUT"
    NETWORK = "NETWORK"
    UNEXPECTED = "UNEXPECTED"


@dataclass
class PageOutcome:
    url: str
    ok: bool
    items_count: int = 0
    failure_category: Optional[ScrapeFailureCategory] = None
    detail: Optional[str] = None


@dataclass
class ScrapeDiagnostics:
    outcomes: list[PageOutcome] = field(default_factory=list)

    @property
    def failures(self) -> list[PageOutcome]:
        return [o for o in self.outcomes if not o.ok]

    @property
    def structure_change_suspected(self) -> list[str]:
        return [
            o.url
            for o in self.outcomes
            if o.failure_category == ScrapeFailureCategory.STRUCTURE_CHANGE
        ]


def _run_coro(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # ループ実行中: 別スレッドで新しいループを回す
    result = {}
    error = {}

    def runner():
        try:
            result["v"] = asyncio.run(coro)
        except BaseException as e:  # noqa
            error["e"] = e

    t = threading.Thread(target=runner)
    t.start()
    t.join()
    if "e" in error:
        raise error["e"]
    return result["v"]


SALE_BON_BASE_URL = "https://www.sale-bon.com"
SALE_BON_KINDLE_URL = "https://www.sale-bon.com/category/kindle"


@dataclass
class SaleItem:
    title: str
    author: Optional[str] = None
    publisher: Optional[str] = None
    asin: Optional[str] = None
    amazon_url: Optional[str] = None
    sale_bon_url: Optional[str] = None
    volume: Optional[str] = None
    sale_type: Optional[str] = None
    discount_rate: Optional[int] = None
    point_rate: Optional[int] = None
    cashback_info: Optional[str] = None
    price: Optional[int] = None
    effective_price: Optional[int] = None
    is_free: bool = False
    is_cheapest: bool = False
    is_high_return: bool = False
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    display_text: Optional[str] = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def normalize_text(text: str) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("　", "").replace(" ", "").strip()
    return normalized.lower()


def _extract_asin_from_url(url: str) -> Optional[str]:
    if not url:
        return None
    import re
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
    return match.group(1) if match else None


def _parse_price(text: str) -> Optional[int]:
    if not text:
        return None
    import re
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _parse_rate(text: str) -> Optional[int]:
    if not text:
        return None
    import re
    match = re.search(r"(\d+)\s*%", text)
    return int(match.group(1)) if match else None


def _parse_book_element(element: Tag, page_url: str) -> Optional[SaleItem]:
    item = SaleItem(title="")

    title_el = element.select_one("h2, h3, .title, .book-title, [class*='title']")
    if title_el:
        item.title = title_el.get_text(strip=True)

    if not item.title:
        return None

    author_el = element.select_one(".author, [class*='author']")
    if author_el:
        item.author = author_el.get_text(strip=True)

    amazon_link = element.select_one("a[href*='amazon.co.jp'], a[href*='amzn']")
    if amazon_link:
        item.amazon_url = cast(str, amazon_link.get("href", ""))
        item.asin = _extract_asin_from_url(item.amazon_url)

    sale_bon_link = element.select_one("a[href^='/'], a[href*='sale-bon.com']")
    if sale_bon_link:
        href = cast(str, sale_bon_link.get("href", ""))
        if href.startswith("/"):
            item.sale_bon_url = SALE_BON_BASE_URL + href
        elif "sale-bon.com" in href:
            item.sale_bon_url = href

    price_el = element.select_one(".price, [class*='price']")
    if price_el:
        item.price = _parse_price(price_el.get_text(strip=True))

    eff_price_el = element.select_one(".effective-price, .real-price, [class*='effective']")
    if eff_price_el:
        item.effective_price = _parse_price(eff_price_el.get_text(strip=True))

    discount_el = element.select_one(".discount, [class*='discount'], [class*='off']")
    if discount_el:
        item.discount_rate = _parse_rate(discount_el.get_text(strip=True))

    point_el = element.select_one(".point, [class*='point']")
    if point_el:
        item.point_rate = _parse_rate(point_el.get_text(strip=True))

    tag_elements = element.select(
        ".tag, .label, .badge, [class*='tag'], [class*='label'], [class*='badge']"
    )
    for tag_el in tag_elements:
        tag_text = tag_el.get_text(strip=True)
        if tag_text:
            item.tags.append(tag_text)

    element_text = element.get_text()

    if any(t in element_text for t in ["最安値", "過去最安値", "最安"]):
        item.is_cheapest = True
        item.sale_type = "最安値"

    if any(t in element_text for t in ["高還元", "ポイント還元"]):
        item.is_high_return = True
        if not item.sale_type:
            item.sale_type = "高還元"

    if any(t in element_text for t in ["無料", "0円", "フリー"]):
        item.is_free = True
        if not item.sale_type:
            item.sale_type = "無料"

    if any(t in element_text for t in ["キャッシュバック", "CB"]):
        if not item.sale_type:
            item.sale_type = "キャッシュバック"
        cashback_el = element.select_one("[class*='cashback']")
        if cashback_el:
            item.cashback_info = cashback_el.get_text(strip=True)

    if not item.sale_type and item.discount_rate:
        item.sale_type = f"{item.discount_rate}%OFF"

    item.display_text = " / ".join(item.tags) if item.tags else item.sale_type

    return item


def _parse_sale_bon_html(soup: BeautifulSoup, page_url: str) -> list[SaleItem]:
    items: list[SaleItem] = []

    book_selectors = [
        "article.book-item",
        "div.book-entry",
        "div.book-card",
        "li.book-item",
        "div[class*='book']",
        "article",
    ]

    book_elements: list[Tag] = []
    for selector in book_selectors:
        book_elements = soup.select(selector)
        if book_elements:
            logger.debug(f"Found {len(book_elements)} items with selector: {selector}")
            break

    if not book_elements:
        amazon_links = soup.select("a[href*='amazon.co.jp']")
        if amazon_links:
            for link in amazon_links[:50]:
                href = cast(str, link.get("href", ""))
                asin = _extract_asin_from_url(href)
                title = link.get_text(strip=True) or cast(str, link.get("title", ""))
                if asin and title:
                    items.append(SaleItem(title=title, asin=asin, amazon_url=href))
        return items

    for element in book_elements[:100]:
        try:
            item = _parse_book_element(element, page_url)
            if item and item.title:
                items.append(item)
        except Exception as e:
            logger.debug(f"Error parsing book element: {e}")

    return items


async def scrape_sale_bon_page_async(
    url: str,
    client: httpx.AsyncClient,
    interval_seconds: int = 2,
    max_retries: int = 3,
    timeout: int = 30,
) -> tuple[list[SaleItem], PageOutcome]:
    outcome = PageOutcome(url=url, ok=False)
    last_exception: Exception | None = None

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                wait_time = interval_seconds * (2 ** (attempt - 1))
                logger.info(f"Retry {attempt} for {url}, waiting {wait_time}s")
                await asyncio.sleep(wait_time)

            response = await client.get(url, timeout=timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            items = _parse_sale_bon_html(soup, url)

            if not items:
                outcome.ok = False
                outcome.failure_category = ScrapeFailureCategory.STRUCTURE_CHANGE
                outcome.detail = "fetched OK but 0 items parsed"
                logger.warning(f"No items found for {url} - possible structure change")
            else:
                outcome.ok = True
                outcome.items_count = len(items)
                logger.info(f"Scraped {len(items)} items from {url}")

            return items, outcome

        except httpx.HTTPStatusError as e:
            last_exception = e
            logger.warning(f"HTTP error {e.response.status_code} for {url}")
            if e.response.status_code in (403, 404, 410):
                outcome.failure_category = ScrapeFailureCategory.HTTP_ERROR
                outcome.detail = f"HTTP {e.response.status_code}"
                return [], outcome
        except httpx.TimeoutException as e:
            last_exception = e
            logger.warning(f"Timeout fetching {url} (attempt {attempt+1})")
        except httpx.TransportError as e:
            last_exception = e
            logger.warning(f"Transport error fetching {url}: {e} (attempt {attempt+1})")
        except Exception as e:
            last_exception = e
            logger.warning(f"Error fetching {url}: {e} (attempt {attempt+1})")

    if last_exception:
        if isinstance(last_exception, httpx.HTTPStatusError):
            outcome.failure_category = ScrapeFailureCategory.HTTP_ERROR
            outcome.detail = f"HTTP {last_exception.response.status_code}"
        elif isinstance(last_exception, httpx.TimeoutException):
            outcome.failure_category = ScrapeFailureCategory.TIMEOUT
            outcome.detail = str(last_exception)
        elif isinstance(last_exception, httpx.TransportError):
            outcome.failure_category = ScrapeFailureCategory.NETWORK
            outcome.detail = str(last_exception)
        else:
            outcome.failure_category = ScrapeFailureCategory.UNEXPECTED
            outcome.detail = str(last_exception)

    logger.error(f"Failed to fetch {url} after {max_retries} retries")
    return [], outcome


async def scrape_sale_bon_async(
    books: list[Any] | None = None,
    interval_seconds: int = 2,
    max_retries: int = 3,
    timeout: int = 30,
    max_concurrency: int = 5,
) -> tuple[list[SaleItem], ScrapeDiagnostics]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; KindleSaleMonitor/1.0; +https://github.com/sota1111/kindle-sale-monitor)",
        "Accept-Language": "ja,en;q=0.5",
    }

    semaphore = asyncio.Semaphore(max_concurrency)

    async def fetch_with_semaphore(url, client):
        async with semaphore:
            items, outcome = await scrape_sale_bon_page_async(
                url, client, interval_seconds, max_retries, timeout
            )
            # Polite pacing: sleep while holding semaphore
            await asyncio.sleep(interval_seconds)
            return items, outcome

    urls_to_fetch = [SALE_BON_KINDLE_URL]
    if books:
        book_sale_bon_urls = [
            b.sale_bon_url
            for b in books
            if getattr(b, "sale_bon_url", None) and getattr(b, "enabled", True)
        ]
        # Unique URLs while preserving order (excluding category URL if present)
        seen_urls = {SALE_BON_KINDLE_URL}
        for url in book_sale_bon_urls:
            if url and url not in seen_urls:
                urls_to_fetch.append(url)
                seen_urls.add(url)

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        tasks = [fetch_with_semaphore(url, client) for url in urls_to_fetch]
        results = await asyncio.gather(*tasks)

    all_items: list[SaleItem] = []
    seen_asins: set[str] = set()
    diagnostics = ScrapeDiagnostics()

    for page_items, outcome in results:
        diagnostics.outcomes.append(outcome)
        for item in page_items:
            if item.asin:
                if item.asin not in seen_asins:
                    seen_asins.add(item.asin)
                    all_items.append(item)
            else:
                all_items.append(item)

    logger.info(f"Total scraped items: {len(all_items)}")
    return all_items, diagnostics


def scrape_sale_bon(
    books: list[Any] | None = None,
    interval_seconds: int = 2,
    max_retries: int = 3,
    timeout: int = 30,
) -> list[SaleItem]:
    items, _ = _run_coro(
        scrape_sale_bon_async(
            books=books,
            interval_seconds=interval_seconds,
            max_retries=max_retries,
            timeout=timeout,
        )
    )
    return items


def scrape_sale_bon_with_diagnostics(
    books: list[Any] | None = None,
    interval_seconds: int = 2,
    max_retries: int = 3,
    timeout: int = 30,
) -> tuple[list[SaleItem], ScrapeDiagnostics]:
    return _run_coro(
        scrape_sale_bon_async(
            books=books,
            interval_seconds=interval_seconds,
            max_retries=max_retries,
            timeout=timeout,
        )
    )
