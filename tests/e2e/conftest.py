"""Fixtures for pytest-playwright admin-dashboard E2E (SOT-1154).

A real uvicorn server is started in a subprocess against a throwaway SQLite DB so the
Playwright browser can drive the live admin UI. This is intentionally separate from the
scraping use of Playwright (which lives in app/services and its unit tests).
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# テストサーバの SessionMiddleware シークレット。テスト側でこの値を使って署名済み
# session クッキーを偽造し、Firebase ログインなしで認証済みページに到達する。
E2E_AUTH_SECRET = "e2e-playwright-secret"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def live_server() -> Iterator[str]:
    port = _free_port()
    db_path = REPO_ROOT / "test_e2e_dashboard.db"
    if db_path.exists():
        db_path.unlink()

    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": f"sqlite:///./{db_path.name}",
            "AUTH_SECRET": E2E_AUTH_SECRET,
            "SEED_SAMPLE_DATA": "false",
            "GOOGLE_CLOUD_PROJECT": "",
            "DISCORD_WEBHOOK_URL": "",
        }
    )

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    try:
        while time.time() < deadline:
            if proc.poll() is not None:
                out = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
                raise RuntimeError(f"uvicorn exited early:\n{out}")
            try:
                with urllib.request.urlopen(f"{base_url}/healthz", timeout=1) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(0.3)
        else:
            raise RuntimeError("uvicorn did not become ready in time")

        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        if db_path.exists():
            db_path.unlink()
