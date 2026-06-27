#!/usr/bin/env python3
"""Local research (price-monitoring) runner for Kindle Sale Monitor.

The deployed Web app is display + Firestore-registration only (SOT-1299); it no
longer triggers research. Run the price check locally with this CLI instead:

    python scripts/run_research.py

Results are persisted through the existing SQLite -> Firestore mirror, so records
created here show up in the Web dashboard. Intended to be scheduled locally (e.g.
via cron).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Allow running as `python scripts/run_research.py` from the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.config import settings as app_settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.services import firestore_sync  # noqa: E402,F401  (attaches Firestore mirror listeners)

logging.basicConfig(
    level=getattr(logging, app_settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("run_research")


def run() -> dict:
    """Execute one full price-check run and return its result summary."""
    # Import here so test stubs can monkeypatch this module's reference.
    import app.models  # noqa: F401  (register ORM models on Base.metadata)
    from app.services.checker import run_check_all

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Best-effort: pull the latest durable state from Firestore before running
        # so a fresh/local SQLite reflects what the Web app has registered.
        try:
            firestore_sync.rehydrate_from_firestore(db)
        except Exception as exc:  # noqa: BLE001 - rehydration must not block a run
            logger.warning("Firestore rehydration skipped: %s", exc)

        result = run_check_all(db)
        return result
    finally:
        db.close()


def main() -> int:
    logger.info("Starting local research run...")
    try:
        result = run()
    except Exception as exc:  # noqa: BLE001 - surface failures with a non-zero exit
        logger.error("Research run failed: %s", exc)
        print(f"Research run failed: {exc}", file=sys.stderr)
        return 1

    logger.info("Research run completed.")
    print("Research run completed. Result:")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
