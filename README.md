# Kindle Sale Monitor

Kindleで購入したい漫画を登録しておき、**Amazon Product Advertising API (PA-API 5.0)** を主データ源として（PA-API 認証情報が無い場合はセール情報サイト「sale-bon」のスクレイピングにフォールバック）定期的に価格・セールを監視し、Discordに通知するシステムです。

## 機能

- ほしい本リストの登録・管理（Webブラウザ管理画面 または Firestore）
- データ取得元を `DATA_SOURCE`（`auto` / `paapi` / `scrape`）で切替（`auto` は PA-API 認証情報があれば PA-API、無ければスクレイピング）
- 定期監視（デフォルト: 1日2回、Cloud Runでは1時間ごと）
- Discord Webhookによるセール通知
- 新規セール・キャッシュバック情報のみ通知（重複通知なし）
- セール履歴・通知履歴の管理
- 本ごとの価格推移グラフ（管理画面の本詳細）
- Webベースの管理画面（ローカル実行時）

## アーキテクチャ（Cloud Run構成）

```
Cloud Scheduler (cron: 0 * * * *)
  └──POST /run──► Cloud Run (FastAPI)
                    ├──► データ取得（data_source ディスパッチャ）
                    │       ├─ Amazon PA-API 5.0 GetItems（主データ源）
                    │       └─ sale-bon.com スクレイピング（フォールバック）
                    ├──► Firestore（セール状態・履歴・通知履歴）
                    └──► Discord Webhook（新規セール検出時のみ）
```

## 認証情報なし開発クイックスタート

本番認証情報（GCP・Discord）なしでもローカル開発・動作確認が可能です。

### 必要なもの
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (推奨) または Python 3.11+ と pip

### 手順

```bash
# 1. リポジトリのクローン
git clone https://github.com/sota1111/kindle-sale-monitor.git
cd kindle-sale-monitor

# 2. 依存パッケージのインストール (uv使用の場合)
uv sync

# 3. 最小設定（認証情報なし）
cp .env.example .env
# .envを開き、コメントアウトされているDISCORD_WEBHOOK_URLはそのままでOK

# 4. サンプルwishlistを使用
cp wishlist.example.json wishlist.json

# 5. 起動
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# 6. 動作確認
curl http://localhost:8000/healthz        # ヘルスチェック
curl -X POST http://localhost:8000/run    # 監視処理実行（通知なし）
```

**動作の違い（認証情報なし時）:**
- `DISCORD_WEBHOOK_URL` 未設定 → 通知はスキップ（ログに "DISCORD_WEBHOOK_URL not set" と出力）
- `GOOGLE_CLOUD_PROJECT` 未設定 → SQLiteで動作（Firestoreは使用しない）

### データ永続化（Firestoreミラー）

Cloud Run のコンテナFSは揮発性で、再起動・再デプロイのたびに SQLite が消えます。これを防ぐため、
`GOOGLE_CLOUD_PROJECT` 設定時は全ドメインのデータ（本リスト / セール履歴 / 通知履歴 / 通知条件 /
アプリ設定）をコミットごとに Firestore へ自動ミラーし、起動時に Firestore から SQLite を復元します。

- 書き込み: SQLAlchemy のコミットイベントで `mirror_*` コレクション（`mirror_books` など）へ二重書き込み（best-effort）
- 復元: 起動時に各 `mirror_*` コレクションを読み戻して SQLite を再構築（本リストのwishlist.jsonシードより先に実行）
- `GOOGLE_CLOUD_PROJECT` 未設定時はミラー・復元とも no-op（従来どおりSQLiteのみ）

## 認証設定

このアプリは Firebase Authentication を使用したログイン認証が必要です。`.env` に以下の変数を設定してください。

### Firebase 設定
Firebase Console > プロジェクト設定 > 全般 > ウェブ API キー から取得してください。

| 変数名 | 説明 |
|--------|------|
| FIREBASE_WEB_API_KEY | Firebase Web API キー（サーバサイドREST認証用・優先）。未設定時は `FIREBASE_API_KEY` にフォールバック |
| FIREBASE_API_KEY | Firebase Web API キー（`FIREBASE_WEB_API_KEY` 未設定時のフォールバック） |

### ユーザー制御
| 変数名 | 説明 | 例 |
|--------|------|-----|
| ALLOWED_USER_EMAILS | ログインを許可するメールアドレス（カンマ区切り） | `your-email@example.com` |
| AUTH_SECRET | セッション署名キー（必ず変更してください） | `random-secret-string` |

### 動作確認方法

1. Firebase Console で「Email/Password」認証を有効にします。
2. ユーザーを作成し、そのメールアドレスを `ALLOWED_USER_EMAILS` に追加します。
3. アプリを起動（`uvicorn app.main:app --reload` または `docker compose up`）
4. http://localhost:8000 にアクセス → ログイン画面にリダイレクトされる
5. Firebase で作成したメールアドレスとパスワードでログイン
6. ログアウトはナビバーの「ログアウト」ボタンから

**注意**: Cloud Scheduler から呼び出される `POST /run` エンドポイントは認証不要です。

## セットアップ（ローカル実行）

### 前提条件

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

### 1. リポジトリのクローン

```bash
git clone https://github.com/sota1111/kindle-sale-monitor.git
cd kindle-sale-monitor
```

### 2. 依存パッケージのインストール

```bash
uv sync
```

### 3. 環境変数の設定

```bash
cp .env.example .env
```

**認証情報なしで動作確認したい場合**: `.env` はそのままでOKです（通知なしモードで動作します）。

**本番利用時**: `.env` を開き、`DISCORD_WEBHOOK_URL` を設定してください。
GCP設定（`GOOGLE_CLOUD_PROJECT`）は省略するとSQLiteでローカル動作します。

### 4. 欲しい本リストの準備（Firestore未使用時）

```bash
cp wishlist.example.json wishlist.json
```

`wishlist.json` を編集して監視したい本を登録してください。

### 5. アプリの起動

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

管理画面: http://localhost:8000

### 6. 動作確認

```bash
# 監視処理を手動実行
curl -X POST http://localhost:8000/run
# ヘルスチェック
curl http://localhost:8000/healthz
```

## Dockerでの実行

```bash
# イメージをビルド
docker build -t kindle-sale-monitor .

# 起動（.envファイルを使用）
docker run --env-file .env -p 8080:8080 kindle-sale-monitor

# 動作確認
curl -X POST http://localhost:8080/run
```

## GCPへのデプロイ

### 前提条件

- Google Cloud SDK（gcloud CLI）インストール済み
- GCPプロジェクト作成済み
- 課金有効化済み

### 1. Firestoreのセットアップ

GCPコンソール → Firestore → 「データベースを作成」

- モード: **ネイティブモード**
- リージョン: `asia-northeast1`（東京）推奨
- データベースID: `(default)` のまま推奨

無料枠: 1GiB storage、50,000読み取り/日、20,000書き込み/日

### 2. Cloud Runへのデプロイ

### GCP Secret Manager セットアップ (Cloud Run本番デプロイ時)

Cloud Run へのデプロイ前に、以下の機密情報をSecret Managerに登録してください。

```bash
# Secret の作成
echo -n "パスワード" | gcloud secrets create kindle-monitor-auth-password --data-file=- --project=YOUR_PROJECT_ID
echo -n "秘密鍵" | gcloud secrets create kindle-monitor-auth-secret-key --data-file=- --project=YOUR_PROJECT_ID
echo -n "Webhook URL" | gcloud secrets create kindle-monitor-discord-webhook-url --data-file=- --project=YOUR_PROJECT_ID

# Cloud Run サービスアカウントに Secret Manager アクセス権を付与
# (デプロイ後、またはデフォルトのコンピュートSAに付与)
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

ローカル開発では `.env` ファイルに値を直接設定してください。

```bash
# gcloud認証
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# イメージをビルドしてContainer Registryへプッシュ
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/kindle-sale-monitor

# Cloud Runへデプロイ（認証必須・Cloud Schedulerからのみ呼ばれる）
gcloud run deploy kindle-sale-monitor \
  --image gcr.io/YOUR_PROJECT_ID/kindle-sale-monitor \
  --platform managed \
  --region asia-northeast1 \
  --no-allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID,DISCORD_WEBHOOK_URL=YOUR_WEBHOOK_URL \
  --memory 512Mi \
  --timeout 300
```

### 3. Cloud Schedulerの設定

```bash
# Cloud Run呼び出し用サービスアカウント作成
gcloud iam service-accounts create kindle-scheduler-sa \
  --display-name "Kindle Sale Monitor Scheduler"

# Cloud Run呼び出し権限を付与
gcloud run services add-iam-policy-binding kindle-sale-monitor \
  --region asia-northeast1 \
  --member serviceAccount:kindle-scheduler-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --role roles/run.invoker

# Cloud RunのURLを取得
CLOUD_RUN_URL=$(gcloud run services describe kindle-sale-monitor \
  --region asia-northeast1 \
  --format='value(status.url)')

# Schedulerジョブ作成（毎時0分に実行）
gcloud scheduler jobs create http kindle-sale-monitor-job \
  --location asia-northeast1 \
  --schedule "0 * * * *" \
  --time-zone "Asia/Tokyo" \
  --uri "${CLOUD_RUN_URL}/run" \
  --http-method POST \
  --oidc-service-account-email kindle-scheduler-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --oidc-token-audience "${CLOUD_RUN_URL}"
```

> **注意**: Cloud Schedulerは **3ジョブまで無料** です。複数の監視を追加する場合は1つのジョブにまとめることを推奨します。

### 4. 欲しい本リストをFirestoreに登録

管理画面（ローカル起動時）またはFirestoreコンソールから `books` コレクションに直接登録してください。

書式:
```json
{
  "title": "本のタイトル",
  "author": "著者名",
  "amazon_url": "https://www.amazon.co.jp/dp/ASIN",
  "asin": "ASIN",
  "enabled": true
}
```

#### 初期監視対象作品サンプル

`wishlist.example.json` には主要な監視対象漫画の初期データが含まれています。
ローカル実行時はそのまま使用できます:

```bash
cp wishlist.example.json wishlist.json
```

Firestore に一括登録する場合は、GCPコンソールの Firestore 画面から `books` コレクションに各エントリを手動で追加するか、Admin SDK を使用してください。

## Cloud Run デプロイ (GitHub Actions)

`main` ブランチへの push（および手動の `workflow_dispatch`）をトリガーに、GitHub Actions が
Docker イメージをビルドして Artifact Registry へ push し、Cloud Run へ自動デプロイします
（`.github/workflows/deploy-cloudrun.yml`）。

- 認証は **Workload Identity Federation** を使用し、JSON サービスアカウントキーは使いません。
- workflow の権限は `contents: read` / `id-token: write` に限定しています。
- フロー: Docker build → Artifact Registry push → `gcloud run deploy`。

### 必要な GitHub Secrets

リポジトリの Settings → Secrets and variables → Actions に以下を登録してください。

| Secret | 説明 |
| --- | --- |
| `GCP_PROJECT_ID` | GCP プロジェクト ID |
| `GCP_REGION` | デプロイ先リージョン（Artifact Registry / Cloud Run） |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Workload Identity プロバイダのリソース名 |
| `GCP_SERVICE_ACCOUNT` | デプロイに使うサービスアカウント |
| `ARTIFACT_REGISTRY_REPOSITORY` | Artifact Registry リポジトリ名 |
| `CLOUD_RUN_SERVICE` | Cloud Run サービス名（`kindle-sale-monitor`） |

## Discord通知の設定

1. Discordサーバーの「サーバー設定」→「連携サービス」→「Webhook」→「新しいWebhookを作成」
2. WebhookのURLをコピー
3. `.env` の `DISCORD_WEBHOOK_URL` に設定
4. Cloud Runへのデプロイ時は `--set-env-vars` に追加

通知条件: 同一セール情報の重複通知を行いません（前回通知済みの割引率・キャッシュバック率と同じ場合はスキップ）。

## 無料枠内での運用

個人利用であれば以下の無料枠内で運用可能です:

| サービス | 無料枠 | 想定使用量 |
|---------|-------|---------|
| Cloud Run | 180,000 vCPU秒/月、360,000 GiB秒/月 | 監視処理は数秒で完了 ✓ |
| Cloud Scheduler | 3ジョブまで無料 | 1ジョブ使用 ✓ |
| Firestore | 50,000読み取り/日、20,000書き込み/日、1GiB | 1回の実行で数読み書き ✓ |
| Container Registry | 0.5GiB/月まで無料 | イメージサイズ次第 |

**前提条件**:
- 監視対象の本は数十冊以内
- Cloud Schedulerは1時間に1回（24ジョブ/日）
- Cloud Runの実行時間は1回あたり300秒以内

## 環境変数

| 変数名 | 必須 | デフォルト | 説明 |
|--------|------|-----------|------|
| `DISCORD_WEBHOOK_URL` | No | — | Discord通知先Webhook URL（未設定時は通知スキップ） |
| `DATABASE_URL` | No | `sqlite:///./kindle_monitor.db` | DB接続URL（ローカル用） |
| `GOOGLE_CLOUD_PROJECT` | No | — | GCPプロジェクトID。設定するとFirestoreが有効になる |
| `FIRESTORE_DATABASE_ID` | No | `(default)` | FirestoreデータベースID |
| `LOCAL_WISHLIST_FILE` | No | `wishlist.json` | ローカル用欲しい本リストファイル |
| `DATA_SOURCE` | No | `auto` | データ取得元: `auto`（PA-API認証情報があればPA-API、無ければスクレイピング）/ `paapi` / `scrape` |
| `PAAPI_ACCESS_KEY` | No | — | Amazon PA-API 5.0 アクセスキー（実データ取得元） |
| `PAAPI_SECRET_KEY` | No | — | Amazon PA-API 5.0 シークレットキー |
| `PAAPI_PARTNER_TAG` | No | — | Amazonアソシエイト パートナータグ |
| `PAAPI_HOST` | No | `webservices.amazon.co.jp` | PA-API ホスト |
| `PAAPI_REGION` | No | `us-west-2` | PA-API リージョン |
| `PAAPI_MARKETPLACE` | No | `www.amazon.co.jp` | PA-API マーケットプレイス |
| `CHECK_INTERVAL_HOURS` | No | `12` | 定期監視間隔（時間、ローカル実行時） |
| `REQUEST_INTERVAL_SECONDS` | No | `2` | sale-bonスクレイピング時のリクエスト間隔（秒） |
| `REQUEST_TIMEOUT_SECONDS` | No | `30` | リクエストタイムアウト（秒） |
| `MAX_RETRIES` | No | `3` | 最大リトライ回数 |
| `LOG_LEVEL` | No | `INFO` | ログレベル |
| `PORT` | No | `8000` | サーバーポート（Cloud Runは自動設定） |

## ログの確認

- **ローカル**: コンソール出力（LOG_LEVEL で制御）
- **Cloud Run**: GCPコンソール → Cloud Run → ログ、または:
  ```bash
  gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=kindle-sale-monitor" --limit 50
  ```

## sale-bon.com 監視時の注意事項（スクレイピング・フォールバック時）

以下は `DATA_SOURCE=scrape`、または `auto` で PA-API 認証情報が未設定のためスクレイピングにフォールバックする場合に適用されます。

- sale-bon.comの利用規約に従い、過度なリクエストを行わないこと
- `REQUEST_INTERVAL_SECONDS` を1秒以上に設定することを推奨
- 購入前にAmazon側の価格・ポイント還元率を必ず確認してください（sale-bonの情報は参考値）
- 本システムは購入の自動化を行いません
