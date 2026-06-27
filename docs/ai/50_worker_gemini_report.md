# Worker Report

## Summary
SOT-1299「構成の最適化」: Web を表示専用 + 入力の Firestore 登録のみにし、リサーチ（価格・セール監視）を
ローカル CLI に移行（案① + 1A + 2A + 3A + 4A）。

**Fallback disclosure:** Both workers were non-responsive — Gemini CLI exited with the
non-response code `75` (`IneligibleTierError: free-tier no longer supported`), and Codex CLI
exited `75` (active usage-limit cooldown). Per the Worker Non-Response Fallback Policy, Claude
Code performed BOTH the implementation and the verification directly. All Quality Gates were
applied unchanged.

## Changed Files
- `app/main.py` — lifespan からアプリ内スケジューラ起動/停止を撤去（4A）。`check`/`run`/`scheduler`
  ルータの import と mount を削除（1A/2A、コードは残置）。rehydrate と表示・登録ルータは維持。
- `app/templates/dashboard.html` — 「手動チェック実行」フォーム/ボタンを撤去（「ほしい本リストを見る」は維持）。
- `scripts/run_research.py`（新規）— ローカル実行 CLI。`firestore_sync` の mirror listener を有効化し、
  起動時に best-effort で `rehydrate_from_firestore` → `run_check_all(db)` を実行（3A、SQLite→Firestore ミラー経由保存）。
- `tests/test_api_scheduler.py`（削除）— 撤去した `/api/scheduler/*` ルータのテスト。
- `tests/test_web_display_only.py`（新規）— `/run`・`/api/check`・`/api/check/all`・`/api/scheduler/jobs` が
  404（未マウント）であること、表示系（`/`・`/books`）が応答することを確認。
- `tests/test_run_research_cli.py`（新規）— CLI の smoke テスト（`run_check_all`/rehydrate をスタブ化、
  正常系で exit 0・失敗系で exit 1）。
- `README.md` / `.env.example` — ローカル運用前提（`python scripts/run_research.py`）に更新。本番定期監視停止（4A）を明記。

## Commands Run
- `ruff check .` → All checks passed!（exit 0）
- `python -m pytest -q` → 137 passed, 7 skipped(既存: async診断はplugin無で従来skip), 10 deselected(e2e marker)（exit 0）
- `python -c "import app.main"` → OK（撤去ルータ参照の残存なし）
- 新規/変更テスト: `tests/test_web_display_only.py` + `tests/test_run_research_cli.py` → 8 passed

## Acceptance Criteria
- [x] Web から /run・/api/check・/api/scheduler が外れた（404）
- [x] 手動チェック UI 撤去
- [x] scripts/run_research.py 新設（run_check_all をローカル実行、ミラー経由保存）
- [x] リサーチ/スケジューラのコードは残置（1A）
- [x] テスト更新・追加が pass
- [x] README/.env.example 更新

## Risks
- 本番（Cloud Run）の定期監視は停止する（4A、承認済み）。リサーチはローカル cron 等で運用する必要がある。
- e2e（`pytest -m e2e`）はライブサーバ前提のため本変更では実行せず（表示系のみ・対象外）。

## Next Action
READY_FOR_REVIEW
