from app.services.scraper import SaleItem, _parse_price, _parse_rate, normalize_text


def test_sale_item_defaults():
    item = SaleItem(title="テスト")
    assert item.title == "テスト"
    assert item.is_free is False
    assert item.is_cheapest is False
    assert item.categories == []
    assert item.tags == []


def test_normalize_text():
    assert normalize_text("　ＴＥＳＴ　") == "test"
    assert normalize_text("") == ""


def test_parse_price():
    assert _parse_price("￥999") == 999
    assert _parse_price(None) is None


def test_parse_rate():
    assert _parse_rate("70%OFF") == 70
    assert _parse_rate(None) is None
