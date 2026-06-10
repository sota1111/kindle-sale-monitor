# Kindle Sale Monitor

Kindleで購入したい漫画を登録しておき、セール情報サイト「sale-bon」を定期的に監視してDiscordに通知するシステムです。

## 機能

- ほしい本リストの登録・管理（Webブラウザ管理画面 または Firestore）
- sale-bonの定期監視（デフォルト: 1日2回、Cloud Runでは1時間ごと）
- Discord Webhookによるセール通知
- 新規セール・キャッシュバック情報のみ通知（重複通知なし）
- セール履歴・通知履歴の管理
- Webベースの管理画面（ローカル実行時）

## アーキテクチャ（Cloud Run構成）

\`\`\`
Cloud Scheduler (cron: 0 * * * *)
  └──POST /run──► Cloud Run (FastAPI)
                    ├──► sale-bon.com スクレイピング
                    ├──► Firestore（セール状態・履歴・通知履歴）
                    └──► Discord Webhook（新規セール検出時のみ）
\`\`\`

## セットアップ（ローカル実行）

### 前提条件

- Python 3.11+
- pip

### 1. リポジトリのクローン

\`\`\`bash
git clone https://github.com/sota1111/kindle-sale-monitor.git
cd kindle-sale-monitor
\`\`\`

### 2. 仮想環境と依存パッケージ

\`\`\`bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
\`\`\`

### 3. 環境変数の設定

\`\`\`bash
cp .env.example .env
\`\`\`

\`.env\` を開き、\`DISCORD_WEBHOOK_URL\` を設定してください。
GCP設定（\`GOOGLE_CLOUD_PROJECT\`）は省略するとSQLiteでローカル動作します。

### 4. 欲しい本リストの準備（Firestore未使用時）

\`\`\`bash
cp wishlist.example.json wishlist.json
\`\`\`

\`wishlist.json\` を編集して監視したい本を登録してください。

### 5. アプリの起動

\`\`\`bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
\`\`\`

管理画面: http://localhost:8000

### 6. 動作確認

\`\`\`bash
# 監視処理を手動実行
curl -X POST http://localhost:8000/run
# ヘルスチェック
curl http://localhost:8000/healthz
\`\`\`

## Dockerでの実行

\`\`\`bash
# イメージをビルド
docker build -t kindle-sale-monitor .

# 起動（.envファイルを使用）
docker run --env-file .env -p 8080:8080 kindle-sale-monitor

# 動作確認
curl -X POST http://localhost:8080/run
\`\`\`

## GCPへのデプロイ

### 前提条件

- Google Cloud SDK（gcloud CLI）インストール済み
- GCPプロジェクト作成済み
- 課金有効化済み

### 1. Firestoreのセットアップ

GCPコンソール → Firestore → 「データベースを作成」

- モード: **ネイティブモード**
- リージョン: \`asia-northeast1\`（東京）推奨
- データベースID: \`(default)\` のまま推奨

無料枠: 1GiB storage、50,000読み取り/日、20,000書き込み/日

### 2. Cloud Runへのデプロイ

\`\`\`bash
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
\`\`\`

### 3. Cloud Schedulerの設定

\`\`\`bash
# Cloud Run呼び出し用サービスアカウント作成
gcloud iam service-accounts create kindle-scheduler-sa \
  --display-name "Kindle Sale Monitor Scheduler"

# Cloud Run呼び出し権限を付与
gcloud run services add-iam-policy-binding kindle-sale-monitor \
  --region asia-northeast1 \
  --member serviceAccount:kindle-scheduler-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --role roles/run.invoker

# Cloud RunのURLを取得
CLOUD_RUN_URL=\$(gcloud run services describe kindle-sale-monitor \
  --region asia-northeast1 \
  --format='value(status.url)')

# Schedulerジョブ作成（毎時0分に実行）
gcloud scheduler jobs create http kindle-sale-monitor-job \
  --location asia-northeast1 \
  --schedule "0 * * * *" \
  --time-zone "Asia/Tokyo" \
  --uri "\${CLOUD_RUN_URL}/run" \
  --http-method POST \
  --oidc-service-account-email kindle-scheduler-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --oidc-token-audience "\${CLOUD_RUN_URL}"
\`\`\`

> **注意**: Cloud Schedulerは **3ジョブまで無料** です。複数の監視を追加する場合は1つのジョブにまとめることを推奨します。

### 4. 欲しい本リストをFirestoreに登録

管理画面（ローカル起動時）またはFirestoreコンソールから \`books\` コレクションに直接登録してください。

書式:
\`\`\`json
{
  "title": "本のタイトル",
  "author": "著者名",
  "amazon_url": "https://www.amazon.co.jp/dp/ASIN",
  "asin": "ASIN",
  "enabled": true
}
\`\`\`

#### 初期監視対象作品サンプル

`wishlist.example.json` には主要な監視対象漫画の初期データが含まれています。
ローカル実行時はそのまま使用できます:

```bash
cp wishlist.example.json wishlist.json
```

Firestore に一括登録する場合は、GCPコンソールの Firestore 画面から `books` コレクションに各エントリを手動で追加するか、Admin SDK を使用してください。

## Discord通知の設定

1. Discordサーバーの「サーバー設定」→「連携サービス」→「Webhook」→「新しいWebhookを作成」
2. WebhookのURLをコピー
3. \`.env\` の \`DISCORD_WEBHOOK_URL\` に設定
4. Cloud Runへのデプロイ時は \`--set-env-vars\` に追加

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
| \`DISCORD_WEBHOOK_URL\` | Yes | — | Discord通知先Webhook URL |
| \`DATABASE_URL\` | No | \`sqlite:///./kindle_monitor.db\` | DB接続URL（ローカル用） |
| \`GOOGLE_CLOUD_PROJECT\` | No | — | GCPプロジェクトID。設定するとFirestoreが有効になる |
| \`FIRESTORE_DATABASE_ID\` | No | \`(default)\` | FirestoreデータベースID |
| \`LOCAL_WISHLIST_FILE\` | No | \`wishlist.json\` | ローカル用欲しい本リストファイル |
| \`CHECK_INTERVAL_HOURS\` | No | \`12\` | 定期監視間隔（時間、ローカル実行時） |
| \`REQUEST_INTERVAL_SECONDS\` | No | \`2\` | sale-bonリクエスト間隔（秒） |
| \`REQUEST_TIMEOUT_SECONDS\` | No | \`30\` | リクエストタイムアウト（秒） |
| \`MAX_RETRIES\` | No | \`3\` | 最大リトライ回数 |
| \`LOG_LEVEL\` | No | \`INFO\` | ログレベル |
| \`PORT\` | No | \`8000\` | サーバーポート（Cloud Runは自動設定） |

## ログの確認

- **ローカル**: コンソール出力（LOG_LEVEL で制御）
- **Cloud Run**: GCPコンソール → Cloud Run → ログ、または:
  \`\`\`bash
  gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=kindle-sale-monitor" --limit 50
  \`\`\`

## sale-bon.com 監視時の注意事項

- sale-bon.comの利用規約に従い、過度なリクエストを行わないこと
- \`REQUEST_INTERVAL_SECONDS\` を1秒以上に設定することを推奨
- 購入前にAmazon側の価格・ポイント還元率を必ず確認してください（sale-bonの情報は参考値）
- 本システムは購入の自動化を行いません
