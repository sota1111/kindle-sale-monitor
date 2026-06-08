# Kindle Sale Monitor

Kindleで購入したい漫画を登録しておき、セール情報サイト「sale-bon」を定期的に監視して通知するシステムです。

## 機能

- ほしい本リストの登録・管理
- sale-bonの定期監視（デフォルト: 1日2回）
- Discord Webhookによるセール通知
- セール履歴・通知履歴の管理
- Webベースの管理画面

## セットアップ手順

### 前提条件

- Python 3.11+
- Docker / docker-compose（オプション）

### 1. リポジトリのクローン

```bash
git clone https://github.com/sota1111/kindle-sale-monitor.git
cd kindle-sale-monitor
```

### 2. 環境変数の設定

```bash
cp .env.example .env
```

`.env` を編集して必要な値を設定してください。

### 3. 依存パッケージのインストール

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. アプリの起動

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

管理画面: http://localhost:8000

## Docker での起動

```bash
docker-compose up -d
```

## 環境変数

| 変数名 | 必須 | デフォルト | 説明 |
|--------|------|-----------|------|
| `DATABASE_URL` | No | `sqlite:///./kindle_monitor.db` | DB接続URL |
| `DISCORD_WEBHOOK_URL` | Yes | — | Discord通知先Webhook URL |
| `CHECK_INTERVAL_HOURS` | No | `12` | 定期監視間隔（時間） |
| `REQUEST_INTERVAL_SECONDS` | No | `2` | sale-bonリクエスト間隔（秒） |
| `REQUEST_TIMEOUT_SECONDS` | No | `30` | リクエストタイムアウト（秒） |
| `MAX_RETRIES` | No | `3` | 最大リトライ回数 |
| `LOG_LEVEL` | No | `INFO` | ログレベル |
| `HOST` | No | `0.0.0.0` | サーバーホスト |
| `PORT` | No | `8000` | サーバーポート |

## 実行方法

### 管理画面

起動後、ブラウザで http://localhost:8000 にアクセス。

- **ほしい本リスト**: 監視したい漫画を登録・管理
- **手動チェック**: ダッシュボードの「手動チェック実行」ボタンで即時実行
- **セール履歴**: 検出されたセール一覧
- **通知履歴**: 送信された通知の記録
- **設定**: 監視間隔などの設定変更

### 本の登録方法

1. 管理画面の「ほしい本リスト」→「新規登録」
2. 以下のいずれかの情報を入力（精度向上のため複数推奨）:
   - 作品名（必須）
   - ASIN（Amazon商品ID）
   - Amazon URL
   - sale-bon URL

### 通知条件

本ごとに以下の通知条件を設定できます（デフォルトはすべて有効）:
- 過去最安値として掲載されたとき
- 高還元として掲載されたとき
- 無料として掲載されたとき
- キャッシュバック対象として掲載されたとき
- 指定割引率以上
- 指定還元率以上
- 指定実質価格以下

## 注意事項

- セール情報はsale-bonの掲載内容に基づきます。購入前に必ずAmazon側の価格・ポイント還元率を確認してください。
- sale-bonへのアクセスはrobots.txtを遵守し、適切なインターバルを設けています。
- DISCORD_WEBHOOK_URLが未設定の場合、通知は送信されません（セール履歴のみ記録されます）。
