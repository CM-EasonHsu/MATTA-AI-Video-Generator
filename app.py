import streamlit as st
import os
import uuid
from google.cloud import storage
from google.oauth2 import service_account
import google.generativeai as genai
import requests
import json
import time
from PIL import Image
import io
from dotenv import load_dotenv
from google.api_core import retry

st.set_page_config(page_title="Video Generation App", layout="wide")

# Initialize Google Cloud Storage client
load_dotenv()
def init_storage_client():
    try:
        # Set project ID
        os.environ["GOOGLE_CLOUD_PROJECT"] = os.getenv("GOOGLE_CLOUD_PROJECT")
        
        # Get credentials path from .env
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        
        if not credentials_path:
            st.error("GOOGLE_APPLICATION_CREDENTIALS not set in .env")
            return None
            
        # Initialize client with service account
        storage_client = storage.Client.from_service_account_json(credentials_path)
        return storage_client
    except Exception as e:
        st.error(f"Failed to initialize Google Cloud Storage client: {e}")
        return None

# 初始化 Gemini
def init_gemini():
    try:
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        # 從環境變數讀取模型名稱，如果沒有設定則使用預設值
        model_name = os.environ.get("GEMINI_MODEL_NAME", "gemini-1.5-pro")
        return genai.GenerativeModel(model_name)
    except Exception as e:
        st.error(f"無法初始化 Gemini: {e}")
        return None

# Upload file to GCS
def upload_to_gcs(bucket_name, file_bytes, destination_blob_name, content_type):
    storage_client = init_storage_client()
    if not storage_client:
        return None
    
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)
        
        # Upload file
        retry_strategy = retry.Retry(deadline=60)
        blob.upload_from_file(
            file_bytes,
            content_type=content_type,
            retry=retry_strategy
        )
        
        return f"https://storage.googleapis.com/{bucket_name}/{destination_blob_name}"
    except Exception as e:
        st.error(f"Error uploading to GCS: {e}")
        return None

# Generate prompt with Gemini
def generate_prompt_with_gemini(text, image_url):
    model = init_gemini()
    if not model:
        return None
    
    try:
        # Download image using storage client
        storage_client = init_storage_client()
        if not storage_client:
            return None
            
        # Parse bucket name and object path from URL
        bucket_name = "matta_storage"
        blob_path = image_url.split(f"{bucket_name}/")[1]
        
        # Get blob
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        
        # Download image content
        st.info(f"Downloading image: {image_url}")
        image_bytes = blob.download_as_bytes()
        
        # Process image
        st.info("Processing image...")
        image = Image.open(io.BytesIO(image_bytes))
        
        # Output image info
        st.info(f"Image mode: {image.mode}, size: {image.size}")
        
        # Ensure RGB mode
        if image.mode != 'RGB':
            st.info(f"Converting image from {image.mode} to RGB")
            image = image.convert('RGB')
            
        # Convert image back to bytes
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='JPEG', quality=95)
        img_byte_arr = img_byte_arr.getvalue()
        
        st.info("Generating prompt...")
        
        # Prompt Gemini to generate Veo2-compatible prompt
        prompt = f"""
        Based on the following text description and image, generate a high-quality prompt suitable for the Veo2 API.
        This prompt should be able to generate a professional video.
        
        User description: {text}
        
        Please generate a detailed, specific, and creative prompt for the Veo2 API to generate a high-quality video.
        """
        
        # Use processed image data
        response = model.generate_content([
            prompt,
            {"mime_type": "image/jpeg", "data": img_byte_arr}
        ])
        
        return response.text
    except Exception as e:
        st.error(f"Error generating prompt with Gemini: {str(e)}")
        st.error(f"Error type: {type(e).__name__}")
        import traceback
        st.error(f"Detailed error: {traceback.format_exc()}")
        return None

# Main application
def main():
    st.title("AI Video Generator")
    st.write("Upload an image and provide a description to generate a professional video")
    
    # Use fixed bucket name
    bucket_name = "matta_storage"
    
    # Main content area
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Upload Content")
        st.write("Please upload an image and describe the video you want to generate")
        
        # Upload area
        with st.container():
            uploaded_file = st.file_uploader(
                "Choose an image",
                type=["jpg", "jpeg", "png"],
                help="Supports JPG, JPEG, and PNG formats"
            )
            
            # Text input
            text_input = st.text_area(
                "Enter description",
                placeholder="Describe the video you want...",
                height=150,
                help="More detailed descriptions lead to better results"
            )
            
            # Button
            if uploaded_file is not None and text_input:
                generate_button = st.button(
                    "Generate Video",
                    type="primary",
                    use_container_width=True
                )
            else:
                generate_button = st.button(
                    "Generate Video",
                    disabled=True,
                    use_container_width=True
                )
        
    with col2:
        st.subheader("Generated Result")
        result_placeholder = st.empty()
    
    if generate_button and uploaded_file is not None and text_input:
        with st.spinner("Processing..."):
            # Generate unique filename
            file_id = str(uuid.uuid4())
            file_extension = os.path.splitext(uploaded_file.name)[1]
            destination_blob_name = f"uploads/{file_id}{file_extension}"
            
            # Reset file pointer and upload to GCS
            uploaded_file.seek(0)
            content_type = f"image/{file_extension[1:]}" if file_extension[1:] != "jpg" else "image/jpeg"
            image_url = upload_to_gcs(bucket_name, uploaded_file, destination_blob_name, content_type)
            
            if image_url:
                st.success("Image uploaded successfully")
                
                # Generate prompt with Gemini
                enhanced_prompt = generate_prompt_with_gemini(text_input, image_url)
                
                if enhanced_prompt:
                    st.success("Enhanced prompt generated")
                    with st.expander("View generated prompt"):
                        st.code(enhanced_prompt)
                    
                    # Call Veo2 API
                    video_response = generate_video_with_veo2(enhanced_prompt)
                    
                    if video_response and "job_id" in video_response:
                        job_id = video_response["job_id"]
                        st.success("Video generation task submitted")
                        
                        # Poll for video status
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        for i in range(100):
                            status = check_video_status(job_id)
                            
                            if status and "status" in status:
                                if status["status"] == "completed":
                                    progress_bar.progress(100)
                                    status_text.success("Video generation completed!")
                                    
                                    if "video_url" in status:
                                        result_placeholder.video(status["video_url"])
                                        with st.expander("Video URL"):
                                            st.code(status["video_url"])
                                    break
                                elif status["status"] == "failed":
                                    progress_bar.progress(100)
                                    status_text.error("Video generation failed")
                                    break
                                else:
                                    progress = status.get("progress", i)
                                    progress_bar.progress(progress)
                                    status_text.info(f"Processing... {progress}%")
                            
                            time.sleep(3)
                    else:
                        st.error("Failed to start video generation task")
                else:
                    st.error("Failed to generate enhanced prompt")
            else:
                st.error("Failed to upload image")
    elif generate_button:
        if not uploaded_file:
            st.warning("Please upload an image")
        if not text_input:
            st.warning("Please enter a description")

if __name__ == "__main__":
    main()