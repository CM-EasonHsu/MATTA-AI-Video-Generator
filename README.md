# AI Video Generator

A Streamlit-based application that allows users to upload images and input text, which are processed by Gemini AI and sent to the Veo2 API to generate professional videos.

## Features

- Upload images to Google Cloud Storage
- Input text descriptions
- Generate enhanced prompts using Google Gemini
- Generate videos using Veo2 API
- Real-time video generation progress display
- Play and download generated videos

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

1. After opening the application, enter your GCS Bucket name in the sidebar (if not set via environment variables)
2. Upload an image
3. Enter descriptive text
4. Click the "Generate Video" button
5. Wait for processing to complete and view the generated video

## Important Notes

- Ensure your GCS Bucket has proper permissions configured
- Gemini API and Veo2 API may require paid subscriptions
- Video generation may take some time, please be patient

## License

[MIT License](LICENSE)