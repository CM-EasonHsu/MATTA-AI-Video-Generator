# AI Video Generator

A Streamlit-based application that allows users to upload images and input text, which are processed by Gemini AI and sent to the Veo2 API to generate professional videos.

## Features

- Upload images to Google Cloud Storage
- Input text descriptions
- Generate enhanced prompts using Google Gemini
- Generate videos using Veo2 API
- Real-time video generation progress display
- Play and download generated videos
- Gallery page to browse all generated videos
- Queue system for managing multiple video generation requests
- Background processing of video generation tasks

## Prerequisites

- Google Cloud Platform account
- Google Cloud Storage bucket
- Gemini API key
- Veo2 API key

## Local Development

1. Clone this repository:
   ```
   git clone <repository-url>
   cd <repository-directory>
   ```

2. Create and activate virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Create `.env` file and set environment variables (refer to `.env.example`):
   ```
   cp .env.example .env
   # Edit .env file with your actual configurations
   ```

5. Run the application:
   ```
   streamlit run app.py
   ```

## Running with Docker

1. Build Docker image:
   ```
   docker build -t ai-video-generator .
   ```

2. Run container:
   ```
   docker run -p 8080:8080 \
     -e GCS_BUCKET_NAME=your-bucket-name \
     -e GEMINI_API_KEY=your-gemini-api-key \
     -e VEO2_API_KEY=your-veo2-api-key \
     ai-video-generator
   ```

## Deploy to Google Cloud Run

1. Ensure Google Cloud CLI is installed and configured:
   ```
   gcloud auth login
   gcloud config set project your-project-id
   ```

2. Build and push Docker image to Google Container Registry:
   ```
   gcloud builds submit --tag gcr.io/your-project-id/ai-video-generator
   ```

3. Deploy to Cloud Run:
   ```
   gcloud run deploy ai-video-generator \
     --image gcr.io/your-project-id/ai-video-generator \
     --platform managed \
     --region asia-east1 \
     --allow-unauthenticated \
     --set-env-vars="GCS_BUCKET_NAME=your-bucket-name,GEMINI_API_KEY=your-gemini-api-key,VEO2_API_KEY=your-veo2-api-key"
   ```

## Usage Instructions

### Generate Video Page
1. After opening the application, enter your GCS Bucket name in the sidebar (if not set via environment variables)
2. Upload an image
3. Enter descriptive text
4. Click the "Generate Video" button
5. Your request will be added to the queue for processing
6. You'll receive a task ID and queue position

### Gallery Page
1. Navigate to the Gallery page using the sidebar
2. Browse all generated videos in a grid layout
3. View video details by expanding the Details section
4. Watch completed videos directly in the browser

### Queue Status Page
1. Navigate to the Queue Status page using the sidebar
2. View all pending tasks in the queue
3. Check the status of recently processed videos
4. Monitor your task's position in the queue

## Important Notes

- Ensure your GCS Bucket has proper permissions configured
- Gemini API and Veo2 API may require paid subscriptions
- Video generation may take some time, please be patient
- The queue system processes one task at a time in the background
- Video metadata and queue information are stored in the 'data' directory
- The background worker thread runs as long as the application is active

## License

[MIT License](LICENSE)