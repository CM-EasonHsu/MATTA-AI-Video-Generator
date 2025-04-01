#!/bin/bash

# 確保腳本在錯誤時停止
set -e

# 讀取環境變數
if [ -f .env ]; then
  export $(cat .env | grep -v '#' | awk '/=/ {print $1}')
fi

# 檢查必要的環境變數
if [ -z "$GCS_BUCKET_NAME" ] || [ -z "$GEMINI_API_KEY" ] || [ -z "$VEO2_API_KEY" ]; then
  echo "錯誤: 缺少必要的環境變數。請確保 .env 文件中包含 GCS_BUCKET_NAME, GEMINI_API_KEY 和 VEO2_API_KEY。"
  exit 1
fi

# 設置 Google Cloud 項目 ID
if [ -z "$GOOGLE_CLOUD_PROJECT" ]; then
  echo "請輸入您的 Google Cloud 項目 ID:"
  read GOOGLE_CLOUD_PROJECT
fi

# 設置應用程式名稱
APP_NAME="ai-video-generator"

# 設置區域
REGION="asia-east1"  # 可以根據需要更改

echo "開始部署 $APP_NAME 到 Google Cloud Run..."

# 構建並推送 Docker 映像
echo "構建並推送 Docker 映像..."
gcloud builds submit --tag gcr.io/$GOOGLE_CLOUD_PROJECT/$APP_NAME

# 部署到 Cloud Run
echo "部署到 Cloud Run..."
gcloud run deploy $APP_NAME \
  --image gcr.io/$GOOGLE_CLOUD_PROJECT/$APP_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars="GCS_BUCKET_NAME=$GCS_BUCKET_NAME,GEMINI_API_KEY=$GEMINI_API_KEY,VEO2_API_KEY=$VEO2_API_KEY"

# 獲取部署的 URL
SERVICE_URL=$(gcloud run services describe $APP_NAME --platform managed --region $REGION --format 'value(status.url)')

echo "部署完成！"
echo "您的應用程式已部署到: $SERVICE_URL"