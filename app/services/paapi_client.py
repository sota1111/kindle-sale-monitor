"""Amazon Product Advertising API (PA-API 5.0) data source.

Fetches current Kindle offers for the wishlist's ASINs via the PA-API ``GetItems``
operation and converts each result into the existing :class:`SaleItem` dataclass so
the existing matcher / checker / notifier pipeline is reused unchanged.

Requests are signed with AWS Signature Version 4 using only the standard library
(``hashlib`` / ``hmac``) plus the already-present ``httpx`` dependency — no new
third-party SDK is introduced.

Credentials (access key / secret key / partner tag) are supplied at deploy time as
Cloud Run secrets. When they are absent the caller falls back to scraping.
"""

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.services.scraper import (
    PageOutcome,
    SaleItem,
    ScrapeDiagnostics,
    ScrapeFailureCategory,
    _extract_asin_from_url,
)

logger = logging.getLogger(__name__)

PAAPI_SERVICE = "ProductAdvertisingAPI"
PAAPI_PATH = "/paapi5/getitems"
PAAPI_TARGET = "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.GetItems"
GET_ITEMS_RESOURCES = [
    "ItemInfo.Title",
    "ItemInfo.ByLineInfo",
    "Offers.Listings.Price",
    "Offers.Listings.SavingBasis",
    "Offers.Listings.LoyaltyPoints",
]
MAX_ITEM_IDS_PER_REQUEST = 10


def paapi_configured(settings: Any) -> bool:
    """True only when all required PA-API credentials are present."""
    return bool(
        getattr(settings, "paapi_access_key", "")
        and getattr(settings, "paapi_secret_key", "")
        and getattr(settings, "paapi_partner_tag", "")
    )


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret_key: str, datestamp: str, region: str, service: str) -> bytes:
    k_date = _sign(("AWS4" + secret_key).encode("utf-8"), datestamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    return _sign(k_service, "aws4_request")


def build_signed_headers(
    *,
    access_key: str,
    secret_key: str,
    region: str,
    host: str,
    payload: str,
    amz_date: str,
) -> dict[str, str]:
    """Build the SigV4-signed header set for a PA-API GetItems request.

    ``amz_date`` is an ISO basic UTC timestamp (``YYYYMMDDTHHMMSSZ``); it is taken as
    an argument so signing is deterministic and unit-testable.
    """
    datestamp = amz_date[:8]
    content_type = "application/json; charset=utf-8"
    content_encoding = "amz-1.0"

    # Canonical request. SignedHeaders must be sorted lowercase header names.
    canonical_headers = (
        f"content-encoding:{content_encoding}\n"
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-date:{amz_date}\n"
        f"x-amz-target:{PAAPI_TARGET}\n"
    )
    signed_headers = "content-encoding;content-type;host;x-amz-date;x-amz-target"
    payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    canonical_request = (
        f"POST\n{PAAPI_PATH}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )

    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{datestamp}/{region}/{PAAPI_SERVICE}/aws4_request"
    string_to_sign = (
        f"{algorithm}\n{amz_date}\n{credential_scope}\n"
        + hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    )

    signing_key = _signing_key(secret_key, datestamp, region, PAAPI_SERVICE)
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    authorization = (
        f"{algorithm} Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    return {
        "host": host,
        "content-type": content_type,
        "content-encoding": content_encoding,
        "x-amz-target": PAAPI_TARGET,
        "x-amz-date": amz_date,
        "Authorization": authorization,
    }


def _collect_asins(books: Optional[list[Any]]) -> list[str]:
    asins: list[str] = []
    seen: set[str] = set()
    for book in books or []:
        if not getattr(book, "enabled", True):
            continue
        asin = getattr(book, "asin", None)
        if not asin:
            asin = _extract_asin_from_url(getattr(book, "amazon_url", None) or "")
        if not asin:
            logger.info(
                "Skipping book without resolvable ASIN: %s",
                getattr(book, "title", "<unknown>"),
            )
            continue
        if asin not in seen:
            seen.add(asin)
            asins.append(asin)
    return asins


def _get(obj: Any, *path: str) -> Any:
    """Safely walk a nested dict by keys, returning None on any miss."""
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _parse_item(item: dict) -> Optional[SaleItem]:
    asin = item.get("ASIN")
    title = _get(item, "ItemInfo", "Title", "DisplayValue")
    if not title:
        return None

    sale = SaleItem(title=title)
    sale.asin = asin
    sale.amazon_url = item.get("DetailPageURL")

    contributors = _get(item, "ItemInfo", "ByLineInfo", "Contributors")
    if isinstance(contributors, list):
        for c in contributors:
            if isinstance(c, dict) and c.get("Role") == "Author" and c.get("DisplayValue"):
                sale.author = c["DisplayValue"]
                break
    sale.publisher = _get(item, "ItemInfo", "ByLineInfo", "Manufacturer", "DisplayValue")

    listings = _get(item, "Offers", "Listings")
    listing = listings[0] if isinstance(listings, list) and listings else None
    if listing:
        amount = _get(listing, "Price", "Amount")
        if amount is not None:
            try:
                sale.price = int(round(float(amount)))
            except (TypeError, ValueError):
                sale.price = None

        if sale.price is not None:
            sale.is_free = sale.price == 0

            pct = _get(listing, "Price", "Savings", "Percentage")
            if isinstance(pct, (int, float)):
                sale.discount_rate = int(pct)
            else:
                basis = _get(listing, "SavingBasis", "Amount")
                if isinstance(basis, (int, float)) and basis > sale.price:
                    sale.discount_rate = int(round((basis - sale.price) / basis * 100))

            points = _get(listing, "LoyaltyPoints", "Points")
            if isinstance(points, (int, float)) and sale.price > 0 and points:
                sale.point_rate = int(round(points / sale.price * 100))
                sale.effective_price = sale.price - int(points)
            else:
                sale.effective_price = sale.price

    if sale.is_free:
        sale.sale_type = "無料"
    elif sale.discount_rate:
        sale.sale_type = f"{sale.discount_rate}%OFF"
    elif sale.point_rate:
        sale.sale_type = f"ポイント{sale.point_rate}%還元"
    sale.display_text = sale.sale_type

    return sale


def _request_batch(
    client: httpx.Client,
    *,
    settings: Any,
    asins: list[str],
    batch_index: int,
    timeout: int,
) -> tuple[list[SaleItem], PageOutcome]:
    host = settings.paapi_host
    url = f"https://{host}{PAAPI_PATH}"
    outcome = PageOutcome(url=f"{url}#batch{batch_index}", ok=False)

    body = {
        "ItemIds": asins,
        "ItemIdType": "ASIN",
        "Resources": GET_ITEMS_RESOURCES,
        "PartnerTag": settings.paapi_partner_tag,
        "PartnerType": "Associates",
        "Marketplace": settings.paapi_marketplace,
    }
    payload = json.dumps(body)
    amz_date = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    headers = build_signed_headers(
        access_key=settings.paapi_access_key,
        secret_key=settings.paapi_secret_key,
        region=settings.paapi_region,
        host=host,
        payload=payload,
        amz_date=amz_date,
    )

    try:
        response = client.post(url, content=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as e:
        outcome.failure_category = ScrapeFailureCategory.HTTP_ERROR
        outcome.detail = f"HTTP {e.response.status_code}"
        logger.warning("PA-API HTTP error %s for batch %s", e.response.status_code, batch_index)
        return [], outcome
    except httpx.TimeoutException as e:
        outcome.failure_category = ScrapeFailureCategory.TIMEOUT
        outcome.detail = str(e)
        logger.warning("PA-API timeout for batch %s", batch_index)
        return [], outcome
    except httpx.TransportError as e:
        outcome.failure_category = ScrapeFailureCategory.NETWORK
        outcome.detail = str(e)
        logger.warning("PA-API transport error for batch %s: %s", batch_index, e)
        return [], outcome
    except Exception as e:  # noqa: BLE001 - never raise out of a fetch
        outcome.failure_category = ScrapeFailureCategory.UNEXPECTED
        outcome.detail = str(e)
        logger.warning("PA-API unexpected error for batch %s: %s", batch_index, e)
        return [], outcome

    items_raw = _get(data, "ItemsResult", "Items") or []
    items: list[SaleItem] = []
    for raw in items_raw:
        if not isinstance(raw, dict):
            continue
        try:
            parsed = _parse_item(raw)
        except Exception as e:  # noqa: BLE001
            logger.debug("Failed to parse PA-API item: %s", e)
            parsed = None
        if parsed:
            items.append(parsed)

    outcome.ok = True
    outcome.items_count = len(items)
    logger.info("PA-API batch %s returned %s items", batch_index, len(items))
    return items, outcome


def fetch_paapi_with_diagnostics(
    books: Optional[list[Any]] = None,
    interval_seconds: int = 2,
    max_retries: int = 3,  # noqa: ARG001 - kept for signature parity with the scraper
    timeout: int = 30,
) -> tuple[list[SaleItem], ScrapeDiagnostics]:
    """Fetch current Kindle offers via PA-API for the wishlist's ASINs.

    Mirrors :func:`app.services.scraper.scrape_sale_bon_async`'s return shape so the
    checker can swap data sources without further changes. Never raises.
    """
    from app.config import settings

    diagnostics = ScrapeDiagnostics()
    asins = _collect_asins(books)
    if not asins:
        logger.info("PA-API: no resolvable ASINs in wishlist; nothing to fetch")
        return [], diagnostics

    all_items: list[SaleItem] = []
    seen_asins: set[str] = set()

    with httpx.Client(timeout=timeout) as client:
        batches = [
            asins[i : i + MAX_ITEM_IDS_PER_REQUEST]
            for i in range(0, len(asins), MAX_ITEM_IDS_PER_REQUEST)
        ]
        for index, batch in enumerate(batches):
            items, outcome = _request_batch(
                client,
                settings=settings,
                asins=batch,
                batch_index=index,
                timeout=timeout,
            )
            diagnostics.outcomes.append(outcome)
            for item in items:
                if item.asin and item.asin in seen_asins:
                    continue
                if item.asin:
                    seen_asins.add(item.asin)
                all_items.append(item)
            # PA-API throttles around 1 TPS; pace politely between batches.
            if index < len(batches) - 1:
                time.sleep(interval_seconds)

    logger.info("PA-API total items: %s", len(all_items))
    return all_items, diagnostics
