"""Tests for the logged-in local browser data source (no real browser launched)."""

import sys
import types
from types import SimpleNamespace

import pytest

from app.services import browser_source, data_source
from app.services.browser_source import (
    _build_sale_item,
    _parse_points,
    fetch_browser_with_diagnostics,
)
from app.services.scraper import ScrapeFailureCategory


def make_book(**kwargs):
    base = dict(asin=None, amazon_url=None, enabled=True, title="本")
    base.update(kwargs)
    return SimpleNamespace(**base)


def make_settings(**overrides):
    base = dict(
        data_source="browser",
        browser_profile_dir="/tmp/kindle-monitor-test-profile",
        browser_headless=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------- #
# Pure parsing
# --------------------------------------------------------------------------- #
def test_parse_points_variants():
    assert _parse_points("500ポイント") == 500
    assert _parse_points("獲得ポイント: 1,200pt") == 1200
    assert _parse_points("ポイント還元") is None
    assert _parse_points(None) is None


def test_build_sale_item_price_and_points():
    item = _build_sale_item(
        "B000000001",
        "https://www.amazon.co.jp/dp/B000000001",
        {
            "title": "テスト本",
            "price_text": "￥500",
            "points_text": "50ポイント",
        },
    )
    assert item is not None
    assert item.asin == "B000000001"
    assert item.price == 500
    assert item.point_rate == 10  # 50 / 500
    assert item.effective_price == 450
    assert item.sale_type == "ポイント10%還元"


def test_build_sale_item_free():
    item = _build_sale_item(
        "B000000002",
        "https://www.amazon.co.jp/dp/B000000002",
        {"title": "無料本", "price_text": "0円"},
    )
    assert item.is_free is True
    assert item.sale_type == "無料"
    assert item.effective_price == 0


def test_build_sale_item_discount_from_list_price():
    item = _build_sale_item(
        "B000000003",
        "https://www.amazon.co.jp/dp/B000000003",
        {"title": "割引本", "price_text": "￥600", "list_price_text": "￥1,000"},
    )
    assert item.discount_rate == 40  # (1000-600)/1000
    assert item.sale_type == "40%OFF"


def test_build_sale_item_structure_change_returns_none():
    assert (
        _build_sale_item("B000000004", "url", {"title": "", "price_text": ""}) is None
    )


# --------------------------------------------------------------------------- #
# fetch_browser_with_diagnostics
# --------------------------------------------------------------------------- #
def _patch_settings(monkeypatch, **overrides):
    import app.config

    s = make_settings(**overrides)
    monkeypatch.setattr(app.config, "settings", s)
    return s


def test_no_asins_returns_empty(monkeypatch):
    _patch_settings(monkeypatch)
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("session should not start without ASINs")

    monkeypatch.setattr(browser_source, "_run_browser_session", boom)

    items, diag = fetch_browser_with_diagnostics(books=[make_book(asin=None)])
    assert items == []
    assert diag.outcomes == []
    assert called["n"] == 0


def test_fetch_collects_asins_and_runs_session(monkeypatch):
    _patch_settings(monkeypatch)
    seen = {}

    def fake_session(asins, **kwargs):
        seen["asins"] = asins
        seen["headless"] = kwargs["headless"]
        from app.services.scraper import PageOutcome, SaleItem, ScrapeDiagnostics

        diag = ScrapeDiagnostics()
        diag.outcomes.append(PageOutcome(url="u", ok=True, items_count=1))
        return [SaleItem(title="本", asin=asins[0])], diag

    monkeypatch.setattr(browser_source, "_run_browser_session", fake_session)

    books = [
        make_book(asin="B000000001"),
        make_book(asin="B000000001"),  # duplicate, must dedupe
        make_book(asin="B000000002", enabled=False),  # disabled, must skip
    ]
    items, diag = fetch_browser_with_diagnostics(books=books)

    assert seen["asins"] == ["B000000001"]
    assert seen["headless"] is True
    assert len(items) == 1
    assert not diag.failures


def test_session_runs_through_fake_playwright(monkeypatch):
    """Drive _run_browser_session end-to-end against an injected fake Playwright."""
    _patch_settings(monkeypatch)

    class FakeTimeoutError(Exception):
        pass

    behavior = {
        "https://www.amazon.co.jp/dp/OK": "ok",
        "https://www.amazon.co.jp/dp/BOOM": "raise",
    }

    class FakePage:
        def __init__(self):
            self.current_url = None

        def goto(self, url, timeout=None, wait_until=None):
            self.current_url = url
            if behavior.get(url) == "raise":
                raise RuntimeError("net::ERR_CONNECTION_REFUSED")

    class FakeContext:
        def __init__(self):
            self.closed = False

        def new_page(self):
            return FakePage()

        def close(self):
            self.closed = True

    class FakeChromium:
        def launch_persistent_context(self, user_data_dir, headless):
            assert user_data_dir  # expanded path passed through
            return FakeContext()

    class FakePW:
        chromium = FakeChromium()

    class FakeSyncCtx:
        def __enter__(self):
            return FakePW()

        def __exit__(self, *a):
            return False

    fake_mod = types.ModuleType("playwright.sync_api")
    fake_mod.sync_playwright = lambda: FakeSyncCtx()
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_mod)

    def extract(page):
        if page.current_url.endswith("/OK"):
            return {"title": "良い本", "price_text": "￥300"}
        return {}

    items, diag = browser_source._run_browser_session(
        ["OK", "BOOM"],
        profile_dir="/tmp/kindle-monitor-test-profile",
        headless=True,
        interval_seconds=0,
        max_retries=1,
        timeout=5,
        extract=extract,
    )

    assert len(items) == 1
    assert items[0].price == 300
    # BOOM page failed and was recorded without raising.
    assert len(diag.failures) == 1
    assert diag.failures[0].failure_category == ScrapeFailureCategory.NETWORK


def test_session_handles_playwright_not_installed(monkeypatch):
    # Make `from playwright.sync_api import sync_playwright` raise ImportError.
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    items, diag = browser_source._run_browser_session(
        ["B000000001"],
        profile_dir="/tmp/kindle-monitor-test-profile",
        headless=True,
        interval_seconds=0,
        max_retries=1,
        timeout=5,
    )
    assert items == []
    assert len(diag.failures) == 1
    assert diag.failures[0].failure_category == ScrapeFailureCategory.UNEXPECTED
    assert "playwright" in diag.failures[0].detail.lower()


# --------------------------------------------------------------------------- #
# Dispatcher wiring
# --------------------------------------------------------------------------- #
def test_dispatch_explicit_browser(monkeypatch):
    import app.config

    monkeypatch.setattr(app.config, "settings", make_settings(data_source="browser"))
    monkeypatch.setattr(
        browser_source, "fetch_browser_with_diagnostics", lambda **k: (["browser"], None)
    )
    items, _ = data_source.fetch_sale_items_with_diagnostics(books=[])
    assert items == ["browser"]


def test_auto_never_selects_browser(monkeypatch):
    import app.config
    from app.services import scraper

    # auto with no PA-API creds must fall back to scrape, never browser.
    monkeypatch.setattr(
        app.config,
        "settings",
        SimpleNamespace(
            data_source="auto",
            paapi_access_key="",
            paapi_secret_key="",
            paapi_partner_tag="",
        ),
    )
    monkeypatch.setattr(
        scraper, "scrape_sale_bon_with_diagnostics", lambda **k: (["scrape"], None)
    )
    items, _ = data_source.fetch_sale_items_with_diagnostics(books=[])
    assert items == ["scrape"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
