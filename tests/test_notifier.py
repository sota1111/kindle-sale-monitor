"""SOT-762: スクレイピング失敗（セレクタ変化等）の Discord 通知の検証テスト。"""

from app.config import settings
from app.services.notifier import send_scrape_failure_notification

SAMPLE_FAILURES = [("STRUCTURE_CHANGE", "https://www.sale-bon.com/category/kindle", "0 items")]


def test_failure_notification_no_webhook(monkeypatch):
    """webhook 未設定なら送信せず False。"""
    monkeypatch.setattr(settings, "discord_webhook_url", "")
    assert send_scrape_failure_notification(SAMPLE_FAILURES) is False


def test_failure_notification_empty_failures(monkeypatch):
    """失敗が無ければ送信不要で True。"""
    monkeypatch.setattr(settings, "discord_webhook_url", "https://example.test/hook")
    assert send_scrape_failure_notification([]) is True


def test_failure_notification_posts_to_discord(monkeypatch):
    """webhook 設定あり: Discord へ content 付きで POST し True を返す。"""
    monkeypatch.setattr(settings, "discord_webhook_url", "https://example.test/hook")

    calls = {}

    class _FakeResponse:
        def raise_for_status(self):
            return None

    def fake_post(url, json=None, timeout=None):
        calls["url"] = url
        calls["json"] = json
        calls["timeout"] = timeout
        return _FakeResponse()

    # notifier は関数内で `import httpx` するため、グローバルの httpx.post を差し替える
    monkeypatch.setattr("httpx.post", fake_post)

    result = send_scrape_failure_notification(SAMPLE_FAILURES)

    assert result is True
    assert calls["url"] == "https://example.test/hook"
    assert "content" in calls["json"]
    assert "STRUCTURE_CHANGE" in calls["json"]["content"]
