from app.services.matcher import match_book_to_sale_item, normalize_text
from app.services.scraper import SaleItem, _extract_asin_from_url, _parse_price, _parse_rate


def test_normalize_text():
    assert normalize_text("テスト") == "テスト"
    assert normalize_text("ＴＥＳＴtest") == "testtest"


def test_extract_asin():
    assert _extract_asin_from_url("https://www.amazon.co.jp/dp/B00TEST123") == "B00TEST123"
    assert _extract_asin_from_url("https://www.amazon.co.jp/gp/product/B00TEST456") == "B00TEST456"
    assert _extract_asin_from_url("https://example.com/no-asin") is None


def test_parse_price():
    assert _parse_price("￥1,234") == 1234
    assert _parse_price("1234円") == 1234
    assert _parse_price("") is None


def test_parse_rate():
    assert _parse_rate("50%") == 50
    assert _parse_rate("50%OFF") == 50
    assert _parse_rate("no rate") is None


class MockBook:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.enabled = True
        self.target_volumes = None
        self.series_watch = False


def test_match_by_asin():
    book = MockBook(asin="B00TEST123", amazon_url=None, sale_bon_url=None,
                    title="テスト漫画", author="作者A", publisher=None)
    sale = SaleItem(title="テスト漫画 1巻", asin="B00TEST123")
    is_match, is_certain = match_book_to_sale_item(book, sale)
    assert is_match is True
    assert is_certain is True


def test_no_match():
    book = MockBook(asin="B00TEST999", amazon_url=None, sale_bon_url=None,
                    title="全く違う本", author="別の作者", publisher=None)
    sale = SaleItem(title="テスト漫画", asin="B00TEST123")
    is_match, _ = match_book_to_sale_item(book, sale)
    assert is_match is False


def test_uncertain_match_title_only():
    book = MockBook(asin=None, amazon_url=None, sale_bon_url=None,
                    title="テスト漫画", author=None, publisher=None)
    sale = SaleItem(title="テスト漫画 1巻", asin="B00TEST123")
    is_match, is_certain = match_book_to_sale_item(book, sale)
    assert is_match is True
    assert is_certain is False
