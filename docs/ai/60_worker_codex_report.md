# Worker Report

## Summary
Initial TASK CHECK for SOT-1299「構成の最適化」(kindle-sale-monitor).

**Fallback disclosure:** Codex CLI was non-responsive (`scripts/ai/run_codex.sh` exited
with the dedicated non-response code `75` due to an active usage-limit cooldown). Per the
Worker Non-Response Fallback Policy, Claude Code performed this read-only task check directly.

SOT-1299 is ACTIONABLE. The PLAN (案① + 1A + 2A + 3A + 4A) was approved by the human
(comment「推奨セットを実行すること。」) and the issue was moved back to Todo → now In Progress.

## Findings (all confirmed by code inspection)
- App-internal scheduler: `app/main.py:103` lifespan → `app/main.py:106,138`
  `start_scheduler(app, interval_hours=interval_hours)` (interval from config). ✓
- `POST /run`: `app/api/run.py:10` `APIRouter(prefix="/run")`, `app/api/run.py:13-20`
  `run_check()` → calls `run_check_all(db)`. Mounted at `app/main.py:162`. ✓
- Dashboard "manual check" UI: `app/templates/dashboard.html:51-52`
  `<form action="/api/check/all">` + 「手動チェック実行」button. ✓
- `/api/check` router: `app/api/check.py:3` (prefix `/api/check`), endpoints `""` and `/all`
  both run `run_check_all` in a background task. Mounted `app/main.py:158`. ✓
- `/api/scheduler` router: `app/api/scheduler.py:6` (prefix `/api/scheduler`), job
  list/pause/resume/reschedule. Mounted `app/main.py:163`. ✓
- Research function for the CLI: `app/services/checker.py:107` `run_check_all(db: Session) -> dict`. ✓
- SQLite→Firestore mirror: `app/services/firestore_sync.py` (mirror on commit +
  `rehydrate_from_firestore` at startup); run history also mirrored via
  `app/services/checker.py:19 _mirror_monitor_log_to_firestore`. ✓ (3A: reuse as-is)
- No existing research CLI under `scripts/` (only `deploy_local_gcp.sh`, `seed_sample_data.py`). ✓
- Test commands: `ruff check .` (lint) and `pytest` (unit/integration). E2E is gated by the
  `e2e` marker: `pytest -m e2e` (needs a live server). No Node/`npm`/typecheck — pure Python.

## Inferred / Approved Acceptance Criteria
- [ ] Web no longer triggers research: app-internal scheduler not started by lifespan;
      `/run`, `/api/check`, `/api/scheduler` routers not mounted; dashboard manual-check UI removed.
- [ ] Research code (checker/scheduler) remains in the repo (1A, reversible).
- [ ] New local CLI `scripts/run_research.py` runs `run_check_all` and persists via the
      existing SQLite→Firestore mirror (3A).
- [ ] Existing unit tests still pass (tests referencing removed routes updated as needed).
- [ ] README / .env.example updated to describe local research operation.

## Classification
IMPLEMENT — approved configuration change, multi-file but single coherent PR.

## Next Action
READY_FOR_REVIEW
