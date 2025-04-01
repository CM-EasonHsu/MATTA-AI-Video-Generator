# AI 影片生成器

這是一個使用 Streamlit 構建的應用程式，允許使用者上傳圖片和輸入文字，透過 Gemini AI 處理後送入 Veo2 API 生成專業影片。

## 功能

- 上傳圖片到 Google Cloud Storage
- 輸入文字描述
- 使用 Google Gemini 生成增強的 prompt
- 調用 Veo2 API 生成影片
- 實時顯示影片生成進度
- 播放和下載生成的影片

## 前置需求

- Google Cloud Platform 帳號
- Google Cloud Storage bucket
- Gemini API 金鑰
- Veo2 API 金鑰

## 本地開發

1. 克隆此儲存庫：
   ```
   git clone <repository-url>
   cd <repository-directory>
   ```

2. 創建並激活虛擬環境：
   ```
   python -m venv venv
   source venv/bin/activate  # 在 Windows 上使用 venv\Scripts\activate
   ```

3. 安裝依賴：
   ```
   pip install -r requirements.txt
   ```

4. 創建 `.env` 文件並設置環境變數（參考 `.env.example`）：
   ```
   cp .env.example .env
   # 編輯 .env 文件填入您的實際配置
   ```

5. 運行應用程式：
   ```
   streamlit run app.py
   ```

## 使用 Docker 運行

1. 構建 Docker 映像：
   ```
   docker build -t ai-video-generator .
   ```

2. 運行容器：
   ```
   docker run -p 8080:8080 \
     -e GCS_BUCKET_NAME=your-bucket-name \
     -e GEMINI_API_KEY=your-gemini-api-key \
     -e VEO2_API_KEY=your-veo2-api-key \
     ai-video-generator
   ```

## 部署到 Google Cloud Run

1. 確保已安裝並配置 Google Cloud CLI：
   ```
   gcloud auth login
   gcloud config set project your-project-id
   ```

2. 構建並推送 Docker 映像到 Google Container Registry：
   ```
   gcloud builds submit --tag gcr.io/your-project-id/ai-video-generator
   ```

3. 部署到 Cloud Run：
   ```
   gcloud run deploy ai-video-generator \
     --image gcr.io/your-project-id/ai-video-generator \
     --platform managed \
     --region asia-east1 \
     --allow-unauthenticated \
     --set-env-vars="GCS_BUCKET_NAME=your-bucket-name,GEMINI_API_KEY=your-gemini-api-key,VEO2_API_KEY=your-veo2-api-key"
   ```

## 使用說明

1. 開啟應用程式後，在側邊欄輸入您的 GCS Bucket 名稱（如果未通過環境變數設置）
2. 上傳一張圖片
3. 輸入描述文字
4. 點擊「生成影片」按鈕
5. 等待處理完成，查看生成的影片

## 注意事項

- 確保您的 GCS Bucket 已正確配置權限
- Gemini API 和 Veo2 API 可能需要付費使用
- 影片生成可能需要一些時間，請耐心等待

## 授權

[MIT License](LICENSE)