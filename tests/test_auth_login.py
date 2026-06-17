"""Tests for 案1 server-side email/password login (SOT-741).

The browser posts email+password to ``POST /session``; the server verifies via
Firebase Identity Toolkit REST. The Identity Toolkit HTTP call is mocked — no
real network access.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app

CSRF = "test-csrf-token"


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
    c = TestClient(app)
    c.cookies.set("csrf_token", CSRF)
    return c


def _post(client, body, *, csrf=CSRF):
    headers = {"X-CSRF-Token": csrf} if csrf is not None else {}
    return client.post("/session", json=body, headers=headers)


def test_login_get_sets_csrf_cookie():
    c = TestClient(app)
    resp = c.get("/login")
    assert resp.status_code == 200
    assert "csrf_token" in resp.cookies
    # No Firebase SDK / signInWithEmailAndPassword in the served page.
    assert "signInWithEmailAndPassword" not in resp.text
    assert "gstatic.com/firebasejs" not in resp.text


def test_login_success_sets_session(client, monkeypatch):
    captured = _patch_identity_toolkit(
        monkeypatch, status_code=200, payload={"email": "allowed@example.com"}
    )
    resp = _post(client, {"email": "allowed@example.com", "password": "secret"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    # password was sent to Identity Toolkit, not logged; request shaped correctly.
    assert captured["params"] == {"key": "test-api-key"}
    assert captured["json"]["returnSecureToken"] is True


def test_login_wrong_password_is_generic_401(client, monkeypatch):
    _patch_identity_toolkit(
        monkeypatch,
        status_code=400,
        payload={"error": {"message": "INVALID_LOGIN_CREDENTIALS"}},
    )
    resp = _post(client, {"email": "allowed@example.com", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json()["error"] == "メールアドレスまたはパスワードが正しくありません"


def test_login_email_not_allowed_is_403(client, monkeypatch):
    _patch_identity_toolkit(monkeypatch, status_code=200, payload={"email": "intruder@example.com"})
    resp = _post(client, {"email": "intruder@example.com", "password": "secret"})
    assert resp.status_code == 403


def test_login_missing_csrf_is_403(client, monkeypatch):
    _patch_identity_toolkit(monkeypatch, status_code=200, payload={"email": "allowed@example.com"})
    resp = _post(client, {"email": "allowed@example.com", "password": "secret"}, csrf=None)
    assert resp.status_code == 403


def test_login_mismatched_csrf_is_403(client, monkeypatch):
    _patch_identity_toolkit(monkeypatch, status_code=200, payload={"email": "allowed@example.com"})
    resp = _post(client, {"email": "allowed@example.com", "password": "secret"}, csrf="other")
    assert resp.status_code == 403


def test_login_missing_api_key_is_500(monkeypatch):
    monkeypatch.delenv("FIREBASE_API_KEY", raising=False)
    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    c = TestClient(app)
    c.cookies.set("csrf_token", CSRF)
    resp = c.post(
        "/session",
        json={"email": "allowed@example.com", "password": "secret"},
        headers={"X-CSRF-Token": CSRF},
    )
    assert resp.status_code == 500
