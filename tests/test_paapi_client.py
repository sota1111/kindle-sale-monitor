"""Tests for the PA-API 5.0 data source (no real network)."""

from types import SimpleNamespace

import httpx
import pytest

from app.services import data_source, paapi_client
from app.services.paapi_client import (
    _collect_asins,
    _parse_item,
    build_signed_headers,
    fetch_paapi_with_diagnostics,
    paapi_configured,
)


def make_settings(**overrides):
    base = dict(
        paapi_access_key="AKIDEXAMPLE",
        paapi_secret_key="SECRETEXAMPLE",
        paapi_partner_tag="mytag-22",
        paapi_host="webservices.amazon.co.jp",
        paapi_region="us-west-2",
        paapi_marketplace="www.amazon.co.jp",
        data_source="auto",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def make_book(**kwargs):
    base = dict(asin=None, amazon_url=None, enabled=True, title="本")
    base.update(kwargs)
    return SimpleNamespace(**base)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=httpx.Request("POST", "https://x"), response=self
            )

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, content=None, headers=None, timeout=None):
        self.calls.append({"url": url, "content": content, "headers": headers})
        if self._exc is not None:
            raise self._exc
        return self._response


# --------------------------------------------------------------------------- #
# paapi_configured
# --------------------------------------------------------------------------- #
def test_paapi_configured_true():
    assert paapi_configured(make_settings()) is True


def test_paapi_configured_false_when_missing():
    assert paapi_configured(make_settings(paapi_secret_key="")) is False
    assert paapi_configured(make_settings(paapi_partner_tag="")) is False
    assert paapi_configured(make_settings(paapi_access_key="")) is False


# --------------------------------------------------------------------------- #
# SigV4 signing
# --------------------------------------------------------------------------- #
def test_build_signed_headers_structure():
    headers = build_signed_headers(
        access_key="AKIDEXAMPLE",
        secret_key="SECRETEXAMPLE",
        region="us-west-2",
        host="webservices.amazon.co.jp",
        payload='{"a":1}',
        amz_date="20260619T220000Z",
    )
    auth = headers["Authorization"]
    assert auth.startswith("AWS4-HMAC-SHA256 ")
    assert "Credential=AKIDEXAMPLE/20260619/us-west-2/ProductAdvertisingAPI/aws4_request" in auth
    assert (
        "SignedHeaders=content-encoding;content-type;host;x-amz-date;x-amz-target" in auth
    )
    assert "Signature=" in auth
    assert headers["x-amz-date"] == "20260619T220000Z"
    assert headers["host"] == "webservices.amazon.co.jp"
    assert headers["content-encoding"] == "amz-1.0"


def test_build_signed_headers_deterministic():
    kwargs = dict(
        access_key="AKIDEXAMPLE",
        secret_key="SECRETEXAMPLE",
        region="us-west-2",
        host="webservices.amazon.co.jp",
        payload='{"a":1}',
        amz_date="20260619T220000Z",
    )
    assert build_signed_headers(**kwargs) == build_signed_headers(**kwargs)


def test_build_signed_headers_signature_changes_with_payload():
    base = dict(
        access_key="AKIDEXAMPLE",
        secret_key="SECRETEXAMPLE",
        region="us-west-2",
        host="webservices.amazon.co.jp",
        amz_date="20260619T220000Z",
    )
    a = build_signed_headers(payload='{"a":1}', **base)["Authorization"]
    b = build_signed_headers(payload='{"a":2}', **base)["Authorization"]
    assert a != b


# --------------------------------------------------------------------------- #
# ASIN collection
# --------------------------------------------------------------------------- #
def test_collect_asins_dedup_and_url_extract():
    books = [
        make_book(asin="B000000001"),
        make_book(asin="B000000001"),  # dup
        make_book(asin=None, amazon_url="https://www.amazon.co.jp/dp/B000000002"),
        make_book(asin=None, amazon_url=None),  # skipped
        make_book(asin="B000000003", enabled=False),  # skipped (disabled)
    ]
    assert _collect_asins(books) == ["B000000001", "B000000002"]


# --------------------------------------------------------------------------- #
# Item parsing
# --------------------------------------------------------------------------- #
def _item(**price_block):
    listing = {"Price": {}}
    listing.update(price_block.pop("listing", {}))
    return {
        "ASIN": "B000000001",
        "DetailPageURL": "https://www.amazon.co.jp/dp/B000000001",
        "ItemInfo": {
            "Title": {"DisplayValue": "テスト書籍"},
            "ByLineInfo": {
                "Contributors": [
                    {"Role": "Author", "DisplayValue": "山田太郎"},
                    {"Role": "Illustrator", "DisplayValue": "別人"},
                ],
                "Manufacturer": {"DisplayValue": "テスト出版"},
            },
        },
        "Offers": {"Listings": [listing]},
    }


def test_parse_item_discount_and_points():
    raw = _item(
        listing={
            "Price": {"Amount": 500, "Savings": {"Percentage": 50}},
            "SavingBasis": {"Amount": 1000},
            "LoyaltyPoints": {"Points": 100},
        }
    )
    item = _parse_item(raw)
    assert item is not None
    assert item.asin == "B000000001"
    assert item.title == "テスト書籍"
    assert item.author == "山田太郎"
    assert item.publisher == "テスト出版"
    assert item.price == 500
    assert item.discount_rate == 50
    assert item.point_rate == 20  # 100 / 500
    assert item.effective_price == 400
    assert item.is_free is False
    assert item.sale_type == "50%OFF"


def test_parse_item_discount_from_saving_basis():
    raw = _item(listing={"Price": {"Amount": 800}, "SavingBasis": {"Amount": 1000}})
    item = _parse_item(raw)
    assert item.discount_rate == 20  # (1000-800)/1000


def test_parse_item_free():
    raw = _item(listing={"Price": {"Amount": 0}})
    item = _parse_item(raw)
    assert item.is_free is True
    assert item.sale_type == "無料"


def test_parse_item_missing_title_returns_none():
    raw = _item()
    raw["ItemInfo"]["Title"] = {}
    assert _parse_item(raw) is None


# --------------------------------------------------------------------------- #
# fetch_paapi_with_diagnostics
# --------------------------------------------------------------------------- #
def _patch_settings(monkeypatch, **overrides):
    import app.config

    s = make_settings(**overrides)
    monkeypatch.setattr(app.config, "settings", s)
    return s


def test_fetch_happy_path(monkeypatch):
    _patch_settings(monkeypatch)
    payload = {
        "ItemsResult": {
            "Items": [
                _item(
                    listing={
                        "Price": {"Amount": 500, "Savings": {"Percentage": 50}},
                        "LoyaltyPoints": {"Points": 50},
                    }
                )
            ]
        }
    }
    fake = FakeClient(response=FakeResponse(payload))
    monkeypatch.setattr(paapi_client.httpx, "Client", lambda *a, **k: fake)

    items, diag = fetch_paapi_with_diagnostics(books=[make_book(asin="B000000001")])

    assert len(items) == 1
    assert items[0].price == 500
    assert items[0].discount_rate == 50
    assert not diag.failures
    assert diag.outcomes[0].ok is True
    assert diag.outcomes[0].items_count == 1
    # Verify the request was signed.
    assert fake.calls[0]["headers"]["Authorization"].startswith("AWS4-HMAC-SHA256 ")


def test_fetch_no_asins_returns_empty(monkeypatch):
    _patch_settings(monkeypatch)
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("should not be called")

    monkeypatch.setattr(paapi_client.httpx, "Client", boom)
    items, diag = fetch_paapi_with_diagnostics(books=[make_book(asin=None)])
    assert items == []
    assert diag.outcomes == []
    assert called["n"] == 0


def test_fetch_http_error_records_failure_no_raise(monkeypatch):
    _patch_settings(monkeypatch)
    fake = FakeClient(response=FakeResponse({}, status_code=429))
    monkeypatch.setattr(paapi_client.httpx, "Client", lambda *a, **k: fake)

    items, diag = fetch_paapi_with_diagnostics(books=[make_book(asin="B000000001")])
    assert items == []
    assert len(diag.failures) == 1
    assert diag.failures[0].detail == "HTTP 429"


def test_fetch_timeout_records_failure(monkeypatch):
    _patch_settings(monkeypatch)
    fake = FakeClient(exc=httpx.TimeoutException("timeout"))
    monkeypatch.setattr(paapi_client.httpx, "Client", lambda *a, **k: fake)

    items, diag = fetch_paapi_with_diagnostics(books=[make_book(asin="B000000001")])
    assert items == []
    assert len(diag.failures) == 1


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #
def test_dispatch_auto_uses_paapi_when_configured(monkeypatch):
    import app.config

    monkeypatch.setattr(app.config, "settings", make_settings(data_source="auto"))
    monkeypatch.setattr(
        paapi_client, "fetch_paapi_with_diagnostics", lambda **k: (["paapi"], None)
    )
    items, _ = data_source.fetch_sale_items_with_diagnostics(books=[])
    assert items == ["paapi"]


def test_dispatch_auto_falls_back_to_scrape(monkeypatch):
    import app.config
    from app.services import scraper

    monkeypatch.setattr(
        app.config, "settings", make_settings(data_source="auto", paapi_access_key="")
    )
    monkeypatch.setattr(
        scraper, "scrape_sale_bon_with_diagnostics", lambda **k: (["scrape"], None)
    )
    items, _ = data_source.fetch_sale_items_with_diagnostics(books=[])
    assert items == ["scrape"]


def test_dispatch_explicit_scrape(monkeypatch):
    import app.config
    from app.services import scraper

    monkeypatch.setattr(app.config, "settings", make_settings(data_source="scrape"))
    monkeypatch.setattr(
        scraper, "scrape_sale_bon_with_diagnostics", lambda **k: (["scrape"], None)
    )
    items, _ = data_source.fetch_sale_items_with_diagnostics(books=[])
    assert items == ["scrape"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
