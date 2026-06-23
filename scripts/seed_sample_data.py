#!/usr/bin/env python3
"""Register provisional (sample) price-history data on the server.

Assumes data could be collected locally; instead it synthesises a realistic
price-trend series for a handful of books so the dashboard can be evaluated.

Usage:
    python scripts/seed_sample_data.py            # idempotent (skips already-seeded books)
    python scripts/seed_sample_data.py --force     # regenerate sample rows
"""

import argparse
import sys
from pathlib import Path

# Allow running directly via `python scripts/seed_sample_data.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.models  # noqa: E402,F401  (registers all ORM models on Base.metadata)
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.services.sample_data import seed_sample_data  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed provisional sample price-history data.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate sample rows even if they already exist.",
    )
    args = parser.parse_args()

    # Ensure tables exist so the script also works against a fresh database
    # (the app normally creates them at startup).
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        result = seed_sample_data(db, force=args.force)
        print(
            f"Seeded {result['books']} book(s), "
            f"{result['sale_history_rows']} price-history row(s)."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
