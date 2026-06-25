"""pytest-playwright scenario E2E for the admin dashboard (SOT-1263 / epic SOT-1258).

These extend the smoke suite in ``test_dashboard_e2e.py`` with user-flow scenarios that
drive real navigation and form submission against the live admin UI and assert on the
resulting URL / visible state. Run with ``pytest -m e2e``.

Authentication reuses the forged Starlette session-cookie helper from the smoke suite, so
no Firebase login round-trip is needed. ``SEED_SAMPLE_DATA=false`` for the e2e server, so
scenarios that need a book create one via the ``/books/new`` form first (the SQLite DB
persists across the session-scoped ``live_server``, so each scenario uses a UNIQUE title).
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import BrowserContext, Page, expect

from tests.e2e.test_dashboard_e2e import _authenticate

pytestmark = pytest.mark.e2e


def _create_book(page: Page, base_url: str, title: str, *, author: str = "") -> None:
    """Create a book via the /books/new form. Leaves the browser on /books."""
    page.goto(f"{base_url}/books/new")
    page.locator("#f-title").fill(title)
    if author:
        page.locator("#f-author").fill(author)
    page.get_by_role("button", name="保存").click()
    expect(page).to_have_url(re.compile(r"/books$"))


def test_scenario_nav_covers_all_sections(
    page: Page, context: BrowserContext, live_server: str
) -> None:
    """S1: 認証後にナビの全リンクを辿り、各遷移先のURLと見出しを確認する。"""
    _authenticate(context, live_server)
    nav = page.locator("nav")
    page.goto(f"{live_server}/")
    expect(page.get_by_role("heading", name="ダッシュボード")).to_be_visible()

    nav.get_by_role("link", name="ほしい本リスト").click()
    expect(page).to_have_url(re.compile(r"/books$"))
    expect(page.get_by_role("heading", name="ほしい本リスト")).to_be_visible()

    nav.get_by_role("link", name="履歴").click()
    expect(page).to_have_url(re.compile(r"/history$"))
    expect(page.get_by_role("heading", name="履歴", exact=True)).to_be_visible()

    nav.get_by_role("link", name="設定").click()
    expect(page).to_have_url(re.compile(r"/settings$"))
    expect(page.get_by_role("heading", name="設定", exact=True)).to_be_visible()

    nav.get_by_role("link", name="ダッシュボード").click()
    expect(page).to_have_url(re.compile(r"127\.0\.0\.1:\d+/$"))
    expect(page.get_by_role("heading", name="ダッシュボード")).to_be_visible()


def test_scenario_register_book_appears_in_list(
    page: Page, context: BrowserContext, live_server: str
) -> None:
    """S2: 一覧→「本を登録」→フォーム送信→一覧に登録した本が表示される。"""
    _authenticate(context, live_server)
    title = "シナリオ登録テスト 進撃の調査"

    page.goto(f"{live_server}/books")
    page.get_by_role("link", name="本を登録").click()
    expect(page).to_have_url(re.compile(r"/books/new$"))

    page.locator("#f-title").fill(title)
    page.locator("#f-author").fill("諫山創")
    page.get_by_role("button", name="保存").click()

    expect(page).to_have_url(re.compile(r"/books$"))
    expect(page.get_by_role("link", name=title)).to_be_visible()


def test_scenario_list_to_book_detail(
    page: Page, context: BrowserContext, live_server: str
) -> None:
    """S3: 一覧の本タイトルをクリックして詳細ページへ遷移する。"""
    _authenticate(context, live_server)
    title = "シナリオ詳細テスト 鋼の錬金術師"
    _create_book(page, live_server, title)

    page.get_by_role("link", name=title).click()
    expect(page).to_have_url(re.compile(r"/books/\d+$"))
    expect(page.get_by_role("heading", name=title)).to_be_visible()
    expect(page.locator("#price-chart")).to_be_visible()


def test_scenario_edit_book_persists(
    page: Page, context: BrowserContext, live_server: str
) -> None:
    """S4: 本を作成→編集で値を変更して保存→変更が反映されている。"""
    _authenticate(context, live_server)
    title = "シナリオ編集テスト 約束のネバーランド"
    new_author = "白井カイウ"
    _create_book(page, live_server, title)

    # Open the book's edit form from the list.
    row = page.locator("tr", has=page.get_by_role("link", name=title))
    row.get_by_role("link", name="編集", exact=True).click()
    expect(page).to_have_url(re.compile(r"/books/\d+/edit$"))
    edit_url = page.url

    page.locator("#f-author").fill(new_author)
    page.get_by_role("button", name="保存").click()
    # Saving redirects to the book detail page.
    expect(page).to_have_url(re.compile(r"/books/\d+$"))

    # Reopen the edit form and confirm the author was persisted.
    page.goto(edit_url)
    expect(page.locator("#f-author")).to_have_value(new_author)


def test_scenario_settings_page_renders(
    page: Page, context: BrowserContext, live_server: str
) -> None:
    """S5: ナビ経由で設定ページに遷移し、見出しと保存ボタンが表示される。"""
    _authenticate(context, live_server)
    page.goto(f"{live_server}/")
    page.locator("nav").get_by_role("link", name="設定").click()
    expect(page).to_have_url(re.compile(r"/settings$"))
    expect(page.get_by_role("heading", name="設定", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="設定を保存")).to_be_visible()


def test_scenario_unauthenticated_protected_page_redirects(
    page: Page, live_server: str
) -> None:
    """S6: 未認証で保護ページにアクセスするとログインへリダイレクトされる。"""
    page.goto(f"{live_server}/books")
    expect(page).to_have_url(re.compile(r"/login"))
    expect(page.locator("input#email")).to_be_visible()
