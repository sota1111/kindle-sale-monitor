from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.notifier import send_scrape_failure_notification
from app.services.scraper import (
    PageOutcome,
    SaleItem,
    ScrapeFailureCategory,
    scrape_sale_bon,
    scrape_sale_bon_async,
    scrape_sale_bon_page_async,
    scrape_sale_bon_with_diagnostics,
)


@pytest.mark.asyncio
async def test_scrape_sale_bon_page_async_success():
    client = AsyncMock(spec=httpx.AsyncClient)
    html = """
    <article class="book-item">
        <h2 class="title">テストタイトル</h2>
    </article>
    """
    client.get.return_value = MagicMock(
        status_code=200,
        text=html
    )

    items, outcome = await scrape_sale_bon_page_async("http://example.com", client)

    assert len(items) == 1
    assert items[0].title == "テストタイトル"
    assert outcome.ok is True
    assert outcome.items_count == 1
    assert outcome.failure_category is None

@pytest.mark.asyncio
async def test_scrape_sale_bon_page_async_structure_change():
    client = AsyncMock(spec=httpx.AsyncClient)
    # 200 OK but empty content that yields 0 items
    client.get.return_value = MagicMock(
        status_code=200,
        text="<html><body>Nothing here</body></html>"
    )

    items, outcome = await scrape_sale_bon_page_async("http://example.com", client)

    assert items == []
    assert outcome.ok is False
    assert outcome.failure_category == ScrapeFailureCategory.STRUCTURE_CHANGE
    assert "0 items" in outcome.detail

@pytest.mark.asyncio
async def test_scrape_sale_bon_page_async_http_error():
    client = AsyncMock(spec=httpx.AsyncClient)
    response = MagicMock(status_code=404)
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=response
    )
    client.get.return_value = response

    # Use max_retries=1 to avoid long wait
    items, outcome = await scrape_sale_bon_page_async("http://example.com", client, max_retries=1)

    assert items == []
    assert outcome.ok is False
    assert outcome.failure_category == ScrapeFailureCategory.HTTP_ERROR
    assert "HTTP 404" in outcome.detail

@pytest.mark.asyncio
async def test_scrape_sale_bon_page_async_timeout():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.side_effect = httpx.TimeoutException("Timeout")

    items, outcome = await scrape_sale_bon_page_async("http://example.com", client, max_retries=1)

    assert items == []
    assert outcome.ok is False
    assert outcome.failure_category == ScrapeFailureCategory.TIMEOUT


@pytest.mark.asyncio
async def test_scrape_sale_bon_page_async_transport_error():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.side_effect = httpx.TransportError("Connection failed")

    items, outcome = await scrape_sale_bon_page_async("http://example.com", client, max_retries=1)

    assert items == []
    assert outcome.ok is False
    assert outcome.failure_category == ScrapeFailureCategory.NETWORK


@pytest.mark.asyncio
async def test_scrape_sale_bon_page_async_unexpected_error():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.side_effect = RuntimeError("Unexpected failure")

    items, outcome = await scrape_sale_bon_page_async("http://example.com", client, max_retries=1)

    assert items == []
    assert outcome.ok is False
    assert outcome.failure_category == ScrapeFailureCategory.UNEXPECTED


@pytest.mark.asyncio
async def test_scrape_sale_bon_async_diagnostics():
    # Mock scrape_sale_bon_page_async to return one success and one failure
    with patch("app.services.scraper.scrape_sale_bon_page_async") as mock_page:
        # Success for first URL (KINDLE_URL)
        item = SaleItem(title="Success Book", asin="B000000001")
        outcome1 = PageOutcome(url="http://kindle", ok=True, items_count=1)

        # Failure for second URL
        outcome2 = PageOutcome(
            url="http://fail",
            ok=False,
            failure_category=ScrapeFailureCategory.HTTP_ERROR,
            detail="HTTP 403",
        )

        mock_page.side_effect = [
            ([item], outcome1),
            ([], outcome2)
        ]

        # Mock books to have one additional URL
        book = MagicMock()
        book.sale_bon_url = "http://fail"
        book.enabled = True

        items, diagnostics = await scrape_sale_bon_async(books=[book], interval_seconds=0)

        assert len(items) == 1
        assert items[0].title == "Success Book"
        assert len(diagnostics.outcomes) == 2
        assert len(diagnostics.failures) == 1
        assert diagnostics.failures[0].url == "http://fail"


def test_scrape_sale_bon_preserves_list_return_type():
    with patch("app.services.scraper.scrape_sale_bon_async", new_callable=AsyncMock) as mock_async:
        item = SaleItem(title="Compatibility Book", asin="B000000001")
        mock_async.return_value = ([item], MagicMock())

        items = scrape_sale_bon()

        assert items == [item]


def test_scrape_sale_bon_with_diagnostics_sync():
    with patch("app.services.scraper.scrape_sale_bon_async", new_callable=AsyncMock) as mock_async:
        from app.services.scraper import ScrapeDiagnostics

        mock_async.return_value = ([], ScrapeDiagnostics())

        items, diagnostics = scrape_sale_bon_with_diagnostics()

        assert items == []
        assert isinstance(diagnostics, ScrapeDiagnostics)


def test_send_scrape_failure_notification_no_webhook():
    with patch("app.config.settings.discord_webhook_url", None):
        success = send_scrape_failure_notification(
            [("STRUCTURE_CHANGE", "http://test.com", "detail")]
        )
        assert success is False


@patch("httpx.post")
def test_send_scrape_failure_notification_success(mock_post):
    mock_post.return_value.status_code = 204
    mock_post.return_value.raise_for_status.return_value = None

    from app.config import settings

    with patch.object(settings, "discord_webhook_url", "http://webhook.com"):
        success = send_scrape_failure_notification([
            ("STRUCTURE_CHANGE", "http://test.com", "detail"),
            ("HTTP_ERROR", "http://test2.com", "403")
        ])
        assert success is True
        args, kwargs = mock_post.call_args
        content = kwargs["json"]["content"]
        assert "STRUCTURE_CHANGE" in content
        assert "http://test.com" in content
        assert "detail" in content
        assert "HTTP_ERROR" in content
        assert "http://test2.com" in content
        assert "403" in content
        assert "推奨アクション" in content
