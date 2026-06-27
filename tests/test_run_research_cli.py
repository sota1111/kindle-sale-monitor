"""SOT-1299: smoke test for the local research CLI (scripts/run_research.py).

The CLI must run `run_check_all` and persist via the existing mirror without
touching the real network/scraper. Everything external is stubbed.
"""

import importlib.util
from pathlib import Path

import pytest

_CLI_PATH = Path(__file__).resolve().parent.parent / "scripts" / "run_research.py"


@pytest.fixture
def cli_module():
    spec = importlib.util.spec_from_file_location("run_research_cli", _CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _DummySession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_run_research_cli_smoke(cli_module, monkeypatch, capsys):
    session = _DummySession()

    monkeypatch.setattr(cli_module, "SessionLocal", lambda: session)
    monkeypatch.setattr(cli_module.Base.metadata, "create_all", lambda *a, **k: None)
    monkeypatch.setattr(
        cli_module.firestore_sync, "rehydrate_from_firestore", lambda db: None
    )

    import app.services.checker as checker

    sentinel = {"checked": 3, "notified": 1}
    monkeypatch.setattr(checker, "run_check_all", lambda db: sentinel)

    rc = cli_module.main()

    assert rc == 0
    assert session.closed is True
    out = capsys.readouterr().out
    assert "Research run completed" in out
    assert "checked" in out


def test_run_research_cli_handles_failure(cli_module, monkeypatch, capsys):
    session = _DummySession()
    monkeypatch.setattr(cli_module, "SessionLocal", lambda: session)
    monkeypatch.setattr(cli_module.Base.metadata, "create_all", lambda *a, **k: None)
    monkeypatch.setattr(
        cli_module.firestore_sync, "rehydrate_from_firestore", lambda db: None
    )

    import app.services.checker as checker

    def _boom(db):
        raise RuntimeError("network down")

    monkeypatch.setattr(checker, "run_check_all", _boom)

    rc = cli_module.main()

    assert rc == 1
    assert session.closed is True
