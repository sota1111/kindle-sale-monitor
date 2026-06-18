#!/usr/bin/env bash
set -euo pipefail

# ローカル gcloud CLI 認証による Cloud Run デプロイスクリプト
# (kindle-sale-monitor)
#
# 使い方:
#   cp .env.example .env && vi .env
#   source .env && bash scripts/deploy_local_gcp.sh

if [ -f .env ]; then set -a; source .env; set +a; fi

PROJECT_ID="${GCP_PROJECT_ID:?GCP_PROJECT_ID is required}"
REGION="${GCP_REGION:-asia-northeast1}"
SERVICE_NAME="${CLOUD_RUN_SERVICE_NAME:-kindle-sale-monitor}"
ARTIFACT_REPO="${ARTIFACT_REGISTRY_REPOSITORY:-kindle-monitor-registry}"
IMAGE_VAR="${IMAGE_NAME:-kindle-sale-monitor}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/${IMAGE_VAR}"

DISCORD_WEBHOOK_URL="${DISCORD_WEBHOOK_URL:-}"
GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-${PROJECT_ID}}"

echo "== Cloud Run デプロイ: ${SERVICE_NAME} =="
echo "Project: ${PROJECT_ID} | Region: ${REGION}"
echo "Image: ${IMAGE}"

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

gcloud artifacts repositories describe "${ARTIFACT_REPO}" \
  --project="${PROJECT_ID}" --location="${REGION}" &>/dev/null || \
gcloud artifacts repositories create "${ARTIFACT_REPO}" \
  --project="${PROJECT_ID}" --location="${REGION}" \
  --repository-format=docker \
  --description="Kindle Sale Monitor Docker images"

gcloud builds submit . \
  --project="${PROJECT_ID}" \
  --tag="${IMAGE}:latest" \
  --timeout=600s

# Secret Manager: 初回デプロイ前に以下を実行してください
# echo -n "value" | gcloud secrets create kindle-monitor-auth-secret --data-file=- --project=$PROJECT_ID
# echo -n "value" | gcloud secrets create kindle-monitor-firebase-api-key --data-file=- --project=$PROJECT_ID
# gcloud run services add-iam-policy-binding kindle-sale-monitor \
#   --member="serviceAccount:$(gcloud run services describe kindle-sale-monitor --region=$REGION --project=$PROJECT_ID --format='value(spec.template.spec.serviceAccountName)' 2>/dev/null || echo PROJECT_NUMBER-compute@developer.gserviceaccount.com)" \
#   --role="roles/secretmanager.secretAccessor" --region=$REGION --project=$PROJECT_ID
#
# 案1（サーバサイドREST認証）でのアクセス到達について:
#   このサービスは --allow-unauthenticated でデプロイされ、Cloud Run IAMは手前で遮断しない。
#   認可はアプリ層で担保する: /login 以外のパスは session cookie 必須（app/auth.py）、
#   ログイン自体は Firebase Identity Toolkit REST でメール/パスワードを検証し、
#   ALLOWED_USER_EMAILS に含まれるメールのみ通過させる。
#   これにより自前の /login ページにブラウザから到達でき、認可はアプリ側で完結する。

# Build --set-secrets string
SET_SECRETS="AUTH_SECRET=kindle-monitor-auth-secret:latest,FIREBASE_API_KEY=kindle-monitor-firebase-api-key:latest"

if [ -n "${DISCORD_WEBHOOK_URL:-}" ]; then
  # ローカルでの動作確認用: Cloud Runでは Secret Manager から取得
  SET_SECRETS="${SET_SECRETS},DISCORD_WEBHOOK_URL=kindle-monitor-discord-webhook-url:latest"
fi

gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE}:latest" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --platform=managed \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${GOOGLE_CLOUD_PROJECT},LOG_LEVEL=${LOG_LEVEL:-INFO},CHECK_INTERVAL_HOURS=${CHECK_INTERVAL_HOURS:-12},PORT=8080,ALLOWED_USER_EMAILS=${ALLOWED_USER_EMAILS:-}" \
  --set-secrets="${SET_SECRETS}" \
  --memory=512Mi \
  --timeout=300 \
  --quiet

URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" --project="${PROJECT_ID}" \
  --format='value(status.url)')

echo ""
echo "== デプロイ完了 =="
echo "Service URL: ${URL}"