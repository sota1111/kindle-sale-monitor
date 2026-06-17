from pathlib import Path

from bs4 import BeautifulSoup

from app.services.scraper import (
    SaleItem,
    _parse_book_element,
    _parse_price,
    _parse_rate,
    _parse_sale_bon_html,
    normalize_text,
)


def load_fixture(name: str) -> str:
    path = Path(__file__).parent / "fixtures" / name
    return path.read_text(encoding="utf-8")


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


def test_parse_book_element_complete():
    html = """
    <article class="book-item">
        <h2 class="title">テストタイトル</h2>
        <div class="author">著者A</div>
        <a href="https://www.amazon.co.jp/dp/B000000000">Amazon</a>
        <div class="price">￥1,200</div>
        <div class="discount">30%OFF</div>
        <div class="tag">タグ1</div>
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    element = soup.select_one("article")
    item = _parse_book_element(element, "http://test.com")

    assert item is not None
    assert item.title == "テストタイトル"
    assert item.author == "著者A"
    assert item.asin == "B000000000"
    assert item.price == 1200
    assert item.discount_rate == 30
    assert "タグ1" in item.tags


def test_parse_book_element_no_title():
    html = '<article class="book-item"><div class="author">著者A</div></article>'
    soup = BeautifulSoup(html, "html.parser")
    element = soup.select_one("article")
    item = _parse_book_element(element, "http://test.com")
    assert item is None


def test_parse_sale_bon_html_normal():
    html = load_fixture("sale_bon_normal.html")
    soup = BeautifulSoup(html, "html.parser")
    items = _parse_sale_bon_html(soup, "http://test.com")

    assert len(items) == 3

    # Item 1
    assert items[0].title == "爆安本 1"
    assert items[0].author == "著者 A"
    assert items[0].price == 1000
    assert items[0].discount_rate == 50
    assert items[0].is_cheapest is True
    assert items[0].sale_type == "最安値"
    assert "Kindle" in items[0].tags
    assert "セール" in items[0].tags

    # Item 2
    assert items[1].title == "爆安本 2"
    assert items[1].author == "著者 B"
    assert items[1].price == 500
    assert items[1].effective_price == 400
    assert items[1].point_rate == 10
    assert items[1].is_high_return is True
    assert items[1].sale_type == "高還元"

    # Item 3
    assert items[2].title == "無料本"
    assert items[2].price == 0
    assert items[2].is_free is True
    assert items[2].sale_type == "無料"


def test_parse_sale_bon_html_amazon_fallback():
    html = load_fixture("sale_bon_amazon_fallback.html")
    soup = BeautifulSoup(html, "html.parser")
    items = _parse_sale_bon_html(soup, "http://test.com")

    # Should find 2 items from amazon links
    assert len(items) == 2
    assert items[0].asin == "B000000004"
    assert items[0].title == "Amazon Link 1"
    assert items[1].asin == "B000000005"
    assert items[1].title == "Amazon Link 2"


def test_parse_sale_bon_html_missing_fields():
    html = load_fixture("sale_bon_missing_fields.html")
    soup = BeautifulSoup(html, "html.parser")
    items = _parse_sale_bon_html(soup, "http://test.com")

    assert len(items) == 1
    assert items[0].title == "欠落本"
    assert items[0].author is None
    assert items[0].price is None


def test_parse_sale_bon_html_structure_changed():
    """
    検証: セレクタがどれにも一致せず、amazonリンクも無い場合、空リストが返る。
    これが返ることは、スクレイピング対象のサイト構造が大幅に変わったことを示唆する。
    """
    html = load_fixture("sale_bon_structure_changed.html")
    soup = BeautifulSoup(html, "html.parser")
    items = _parse_sale_bon_html(soup, "http://test.com")

    assert isinstance(items, list)
    assert len(items) == 0


def test_parse_sale_bon_html_empty():
    html = load_fixture("sale_bon_empty.html")
    soup = BeautifulSoup(html, "html.parser")
    items = _parse_sale_bon_html(soup, "http://test.com")

    assert len(items) == 0


def test_parse_health_check():
    """
    正常系と構造変化系を対比し、パースの「健全性」を検証する。
    """
    # 正常系
    normal_html = load_fixture("sale_bon_normal.html")
    normal_items = _parse_sale_bon_html(BeautifulSoup(normal_html, "html.parser"), "http://test.com")
    assert len(normal_items) > 0, "Normal HTML should yield items"

    # 構造変化系
    changed_html = load_fixture("sale_bon_structure_changed.html")
    changed_items = _parse_sale_bon_html(BeautifulSoup(changed_html, "html.parser"), "http://test.com")
    assert len(changed_items) == 0, "Changed structure should yield 0 items (signaling failure)"
