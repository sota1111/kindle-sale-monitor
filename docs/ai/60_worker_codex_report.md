# Worker Report

## Summary
Initial TASK CHECK for SOT-1153「仮データ登録とダッシュボード改修」(kindle-sale-monitor).

**Worker non-response disclosure:** Codex CLI was non-responsive for this task check —
`scripts/ai/run_codex.sh` exited with the dedicated non-response code `75`
(`CODEX_COOLDOWN_ACTIVE`, usage-limit cooldown until epoch 1782609660 ≈ ~4 days out).
Per the Worker Non-Response Fallback Policy, Claude Code performed this task check directly.

**Verdict: actionable (YES).** Single cohesive feature: seed provisional price-history sample
data + revamp the dashboard to visualize it.

## Architecture findings
- Stack: FastAPI + SQLAlchemy + Jinja2 server-rendered templates (no SPA). SQLite locally
  (`kindle_monitor.db`), Firestore mirror on Cloud Run.
- Price/sale data model: `app/models/sale_history.py` `SaleHistory` (book_id FK, price,
  effective_price, discount_rate, point_rate, is_cheapest, is_free, fetched_at, notified, ...).
- Existing endpoints (`app/api/history.py`): `GET /api/sales`, `GET /api/books/{id}/price-history`
  (schema `PriceHistoryPoint`), `GET /api/notifications`, `GET /api/monitor-logs`.
- Dashboard surface: `app/main.py` `GET /` → `app/templates/dashboard.html`. Currently minimal:
  book_count, pending_count, recent_sales (5), recent_notifications (5). NO chart, NO aggregates.
- Per-book price chart already exists in `book_detail.html` (Chart.js v4 via CDN, fetches
  `/api/books/{id}/price-history`).
- Seed mechanism: `app/services/seeder.py` `seed_books_from_wishlist()` (Books only, from
  `wishlist.json`); run at startup via `_seed_books()` in `main.py`. NO sale-history seeder exists.
- Config: `app/config.py` pydantic-settings (`data_source` auto|paapi|scrape|browser, etc.).
- i18n: client-side ja→en dictionary in `app/templates/base.html` (SOT-953); new UI strings must
  be added to the `DICT`.

## Recommended approach (file list)
1. `app/services/sample_data.py` — idempotent `seed_sample_data(db)` generating ~90 days of
   realistic `SaleHistory` price-trend points for a few books (marker `sale_type="sample"`).
2. `app/config.py` — add `seed_sample_data: bool = False` (env `SEED_SAMPLE_DATA`).
3. `app/main.py` — `_seed_sample_data()` startup hook gated on the flag; enrich `GET /` context
   with aggregate KPIs.
4. `scripts/seed_sample_data.py` — CLI to register provisional data on demand.
5. `app/api/dashboard.py` (or extend history.py) — `GET /api/dashboard/summary` +
   `GET /api/dashboard/price-trends` (multi-book series for the chart).
6. `app/templates/dashboard.html` — KPI cards + multi-series price-trend Chart.js + "値下げ中" table.
7. `app/templates/base.html` — new i18n DICT entries.
8. `tests/test_sample_data.py`, `tests/test_api_dashboard.py` — follow existing test patterns.
9. `.env.example` / `README.md` — document `SEED_SAMPLE_DATA`.

## Commands Run
- `bash scripts/ai/run_codex.sh` → exit 75 (cooldown, non-responsive).
- Repo inspection (ls/cat/grep) by Claude Code fallback.

## Acceptance Criteria (derived)
- [x] Issue is actionable
- [x] Implementation surface located
- [x] Quality gate commands identified

## Quality gate commands
- Lint: `ruff check app tests`
- Typecheck: `mypy app`
- Test: `pytest` (pytest + pytest-asyncio; SQLite test DBs per module)
- No npm/e2e (pure Python project).

## Risks
- Startup seeding must be flag-gated so provisional data never lands in production unintentionally.
- New aggregate endpoints must tolerate empty data (no history) gracefully.
- i18n: dynamic DB values must not collide with DICT keys (existing convention already handles this).

## Next Action
READY_FOR_REVIEW
