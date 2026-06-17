"""SOT-762: スクレイピング堅牢化（リトライ・セレクタ変化検知）の検証テスト。

本体ロジック（`scrape_sale_bon_page_async` のリトライ／構造変化検知）は実装済みのため、
ここではその挙動を HTTP モック（`httpx.MockTransport`）で裏付ける。
非同期関数は各テスト内で `asyncio.run` を使って実行し、pytest-asyncio 設定には依存しない。
`interval_seconds=0` を渡してバックオフ待機を実質ゼロにし高速化する。
"""

import asyncio

import httpx

from app.services.scraper import (
    PageOutcome,
    ScrapeDiagnostics,
    ScrapeFailureCategory,
    scrape_sale_bon_page_async,
)

TEST_URL = "https://www.sale-bon.com/category/kindle"

NORMAL_HTML = (
    '<article class="book-item"><h2 class="title">本</h2>'
    '<a href="https://www.amazon.co.jp/dp/B000000000">A</a></article>'
)

# book 要素も amazon リンクも無い = サイト構造変化を示唆する HTML
STRUCTURE_CHANGED_HTML = "<html><body><p>no books</p></body></html>"


def _run(handler, **kwargs):
    transport = httpx.MockTransport(handler)

    async def _go():
        async with httpx.AsyncClient(transport=transport) as client:
            return await scrape_sale_bon_page_async(
                TEST_URL, client, interval_seconds=0, **kwargs
            )

    return asyncio.run(_go())


def test_retry_then_success():
    """一時失敗が2回続いた後、3回目で成功する（リトライが効いている）。"""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, text=NORMAL_HTML)

    items, outcome = _run(handler, max_retries=3)

    assert calls["n"] == 3
    assert outcome.ok is True
    assert len(items) >= 1


def test_retry_exhausted_timeout():
    """タイムアウトが続くとリトライを使い切り、TIMEOUT に分類される。"""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectTimeout("t")

    items, outcome = _run(handler, max_retries=3)

    assert items == []
    assert outcome.ok is False
    assert outcome.failure_category == ScrapeFailureCategory.TIMEOUT
    assert calls["n"] == 3


def test_retry_exhausted_network():
    """ネットワークエラーが続くとリトライを使い切り、NETWORK に分類される。"""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectError("net")

    items, outcome = _run(handler, max_retries=3)

    assert items == []
    assert outcome.ok is False
    assert outcome.failure_category == ScrapeFailureCategory.NETWORK
    assert calls["n"] == 3


def test_http_error_no_retry():
    """404 など恒久エラーはリトライせず即座に HTTP_ERROR を返す。"""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404, text="not found")

    items, outcome = _run(handler, max_retries=3)

    assert items == []
    assert outcome.ok is False
    assert outcome.failure_category == ScrapeFailureCategory.HTTP_ERROR
    # リトライしない: ハンドラは1回のみ呼ばれる
    assert calls["n"] == 1


def test_structure_change_detected():
    """200 OK だがパース結果0件 → STRUCTURE_CHANGE（セレクタ変化検知）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=STRUCTURE_CHANGED_HTML)

    items, outcome = _run(handler, max_retries=3)

    assert items == []
    assert outcome.ok is False
    assert outcome.failure_category == ScrapeFailureCategory.STRUCTURE_CHANGE
    assert outcome.detail == "fetched OK but 0 items parsed"


def test_diagnostics_structure_change_suspected():
    """ScrapeDiagnostics が STRUCTURE_CHANGE の URL を failures / 監視対象に集約する。"""
    outcome = PageOutcome(
        url=TEST_URL,
        ok=False,
        failure_category=ScrapeFailureCategory.STRUCTURE_CHANGE,
        detail="fetched OK but 0 items parsed",
    )
    diag = ScrapeDiagnostics()
    diag.outcomes.append(outcome)

    assert outcome in diag.failures
    assert TEST_URL in diag.structure_change_suspected
