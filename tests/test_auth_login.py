"""Tests for 案1 server-side email/password login.

The browser posts email+password as Form data to ``POST /login``; the server verifies via
Firebase Identity Toolkit REST. The Identity Toolkit HTTP call is mocked — no
real network access.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app


def _patch_identity_toolkit(monkeypatch, *, status_code=200, payload=None, raise_error=False):
    """Patch app.main.httpx.AsyncClient so no real network call is made."""
    captured: dict = {}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, params=None, json=None):
            captured["url"] = url
            captured["params"] = params
            captured["json"] = json
            if raise_error:
                import httpx

                raise httpx.ConnectError("boom")
            return SimpleNamespace(status_code=status_code, json=lambda: payload or {})

    monkeypatch.setattr("app.main.httpx.AsyncClient", _FakeAsyncClient)
    return captured


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("FIREBASE_API_KEY", "test-api-key")
    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    c = TestClient(app)
    return c


def _post(client, data):
    # follow_redirects=False to check the 303/302 response
    return client.post("/login", data=data, follow_redirects=False)


def test_login_page_get(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "Kindle Sale Monitor" in resp.text


def test_login_success_redirects_to_dashboard(client, monkeypatch):
    _patch_identity_toolkit(
        monkeypatch, status_code=200, payload={"email": "allowed@example.com"}
    )
    resp = _post(client, {"email": "allowed@example.com", "password": "secret"})
    # Success: Redirect to / (303)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


def test_login_wrong_password_shows_error(client, monkeypatch):
    _patch_identity_toolkit(
        monkeypatch,
        status_code=400,
        payload={"error": {"message": "INVALID_LOGIN_CREDENTIALS"}},
    )
    resp = _post(client, {"email": "allowed@example.com", "password": "wrong"})
    # Failure: Re-render login page with 401
    assert resp.status_code == 401
    assert "メールアドレスまたはパスワードが正しくありません" in resp.text


def test_login_email_not_allowed_shows_error(client, monkeypatch):
    _patch_identity_toolkit(monkeypatch, status_code=200, payload={"email": "intruder@example.com"})
    resp = _post(client, {"email": "intruder@example.com", "password": "secret"})
    # Failure: Re-render login page with 403
    assert resp.status_code == 403
    assert "このメールアドレスは許可されていません" in resp.text


def test_login_missing_api_key_is_500(monkeypatch):
    monkeypatch.delenv("FIREBASE_API_KEY", raising=False)
    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    c = TestClient(app)
    resp = c.post(
        "/login",
        data={"email": "allowed@example.com", "password": "secret"},
    )
    assert resp.status_code == 500
    assert "サーバ設定エラーです" in resp.text
