# Worker Report

## Summary
SOT-1140: added a logged-in local browser data source (`browser`) that drives a Playwright
persistent-profile Chromium over each wishlist book's `https://www.amazon.co.jp/dp/<asin>`
product page and reads Kindle price / points / discount / free status into the existing
`SaleItem`, keeping the checker source-agnostic. Opt-in via `DATA_SOURCE=browser`; `auto`
never selects it.

Gemini CLI was non-responsive (IneligibleTierError / exit 1 → treated as exit 75), so under the
Worker Non-Response Fallback Policy Claude Code implemented this directly.

## Changed Files
- `app/services/browser_source.py` — NEW. `fetch_browser_with_diagnostics(books, …)` →
  `(list[SaleItem], ScrapeDiagnostics)`, never raises. Persistent-profile Chromium via
  `launch_persistent_context(user_data_dir, headless)`, one context, per-ASIN `/dp/` visit with
  retries + polite pacing, run on a dedicated thread (Playwright sync API can't share a running
  asyncio loop). Pure `_build_sale_item` / `_parse_points` for parsing; missing Playwright or
  launch failure recorded as a `PageOutcome`, never crashes.
- `app/services/data_source.py` — dispatcher: `_resolve_source` recognizes `browser`;
  `fetch_sale_items_with_diagnostics` routes to `fetch_browser_with_diagnostics`. `auto` unchanged
  (never picks browser). Module docstring updated.
- `app/config.py` — `Settings` += `browser_profile_dir` (default `~/.kindle-monitor/browser-profile`)
  and `browser_headless` (default `True`); `data_source` doc updated to include `browser`.
- `.env.example` — documents `DATA_SOURCE=browser` and the new `BROWSER_PROFILE_DIR` /
  `BROWSER_HEADLESS` vars + `playwright install chromium` prep note (local-PC only).
- `pyproject.toml` — added `playwright>=1.44.0` to dependencies.
- `tests/test_browser_source.py` — NEW. 11 tests, no real browser launched (fake Playwright via
  `sys.modules`): point/price/free/discount parsing, structure-change `None`, ASIN dedupe + enabled
  filtering, end-to-end session loop incl. NETWORK failure recording, Playwright-not-installed path,
  and dispatcher wiring (`DATA_SOURCE=browser`, `auto` never picks browser).

## Commands Run
- `uv run --no-sync ruff check .` → All checks passed (exit 0)
- `uv run --no-sync mypy app` → Success: no issues found in 42 source files (exit 0)
- `uv run --no-sync pytest -q` → 136 passed (was 125; +11 new) (exit 0)

## Acceptance Criteria
- [x] New `browser` data source returning `(list[SaleItem], ScrapeDiagnostics)`
- [x] Playwright persistent profile (Q1①), per-`/dp/<asin>` traversal (Q2①)
- [x] Opt-in only; `auto` never selects browser
- [x] Never raises; failures recorded as diagnostics
- [x] Config + `.env.example` + dependency wired
- [x] lint / typecheck / tests green

## Risks
- `playwright` runtime + `playwright install chromium` must be installed locally; not run here
  (offline `--no-sync`). The source degrades to a single UNEXPECTED diagnostic if absent.
- Headed first-login and a desktop profile are local-PC only (not Cloud Run).
- Amazon TOS / bot-detection on automating a logged-in session — operator's call; pacing via the
  existing interval knobs.
- `/dp` page selectors are best-effort and may need tuning against the live Amazon DOM.

## Fallback Disclosure (audit)
- Non-responsive worker: Gemini CLI (IneligibleTierError, exit 1) AND Codex CLI (usage-limit
  cooldown, exit 75).
- Claude Code performed implementation and verification directly per the Worker Non-Response
  Fallback Policy. All Quality Gates applied unchanged.

## Next Action
READY_FOR_REVIEW
