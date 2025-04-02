import streamlit as st
import os
import uuid
from google.cloud import storage
from google.oauth2 import service_account
import google.generativeai as genai
import requests
import json
import time
import datetime
import threading
import pickle
from PIL import Image
import io
from dotenv import load_dotenv
from google.api_core import retry
from collections import deque

st.set_page_config(page_title="Video Generation App", layout="wide")

# Path for storing video metadata and queue
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
VIDEOS_DB_PATH = os.path.join(DATA_DIR, 'videos.pkl')
QUEUE_DB_PATH = os.path.join(DATA_DIR, 'queue.pkl')

# Create data directory if it doesn't exist
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

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
        # 修改 URL 解析邏輯
        if "storage.googleapis.com" in image_url:
            # 從完整 URL 解析
            parts = image_url.split("storage.googleapis.com/")
            if len(parts) > 1:
                full_path = parts[1]
                bucket_name, *path_parts = full_path.split("/", 1)
                blob_path = path_parts[0] if path_parts else ""
            else:
                st.error("Invalid storage URL format")
                return None
        else:
            st.error("Invalid storage URL")
            return None
        
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
# 調用 Veo2 API 生成影片
def generate_video_with_veo2(prompt):
    try:
        veo2_api_key = os.environ.get("VEO2_API_KEY")
        veo2_api_url = "https://api.veo2.com/v1/generate"  # 請替換為實際的 Veo2 API 端點
        
        headers = {
            "Authorization": f"Bearer {veo2_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "prompt": prompt,
            "format": "mp4",
            "duration": 15  # 假設默認生成 15 秒的影片
        }
        
        response = requests.post(veo2_api_url, headers=headers, json=payload)
        response.raise_for_status()
        
        return response.json()
    except Exception as e:
        st.error(f"調用 Veo2 API 時出錯: {e}")
        return None

# 檢查影片生成狀態
def check_video_status(job_id):
    try:
        veo2_api_key = os.environ.get("VEO2_API_KEY")
        veo2_status_url = f"https://api.veo2.com/v1/status/{job_id}"  # 請替換為實際的 Veo2 API 端點
        
        headers = {
            "Authorization": f"Bearer {veo2_api_key}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(veo2_status_url, headers=headers)
        response.raise_for_status()
        
        return response.json()
    except Exception as e:
        st.error(f"檢查影片狀態時出錯: {e}")
        return None

# Video database management functions
def load_videos_db():
    if os.path.exists(VIDEOS_DB_PATH):
        try:
            with open(VIDEOS_DB_PATH, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            st.error(f"Error loading videos database: {e}")
    return []

def save_videos_db(videos):
    try:
        with open(VIDEOS_DB_PATH, 'wb') as f:
            pickle.dump(videos, f)
        return True
    except Exception as e:
        st.error(f"Error saving videos database: {e}")
        return False

def add_video_to_db(video_data):
    videos = load_videos_db()
    videos.append(video_data)
    return save_videos_db(videos)

# Queue management functions
def load_queue():
    if os.path.exists(QUEUE_DB_PATH):
        try:
            with open(QUEUE_DB_PATH, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            st.error(f"Error loading queue: {e}")
    return deque()

def save_queue(queue):
    try:
        with open(QUEUE_DB_PATH, 'wb') as f:
            pickle.dump(queue, f)
        return True
    except Exception as e:
        st.error(f"Error saving queue: {e}")
        return False

def add_to_queue(task):
    queue = load_queue()
    queue.append(task)
    return save_queue(queue)

def get_next_from_queue():
    queue = load_queue()
    if queue:
        task = queue.popleft()
        save_queue(queue)
        return task
    return None

def get_queue_position(task_id):
    queue = load_queue()
    for i, task in enumerate(queue):
        if task['id'] == task_id:
            return i + 1
    return None

# Background worker to process the queue
def process_queue_worker():
    while True:
        task = get_next_from_queue()
        if task:
            try:
                # Process the task
                enhanced_prompt = task['enhanced_prompt']
                task_id = task['id']
                
                # Call Veo2 API
                video_response = generate_video_with_veo2(enhanced_prompt)
                
                if video_response and "job_id" in video_response:
                    job_id = video_response["job_id"]
                    
                    # Poll for video status
                    for _ in range(20):  # Try for about 1 minute
                        status = check_video_status(job_id)
                        
                        if status and "status" in status:
                            if status["status"] == "completed":
                                if "video_url" in status:
                                    # Add completed video to database
                                    video_data = {
                                        'id': task_id,
                                        'timestamp': datetime.datetime.now().isoformat(),
                                        'description': task['description'],
                                        'prompt': enhanced_prompt,
                                        'video_url': status["video_url"],
                                        'thumbnail_url': task.get('image_url', ''),
                                        'status': 'completed'
                                    }
                                    add_video_to_db(video_data)
                                break
                            elif status["status"] == "failed":
                                # Add failed video to database
                                video_data = {
                                    'id': task_id,
                                    'timestamp': datetime.datetime.now().isoformat(),
                                    'description': task['description'],
                                    'prompt': enhanced_prompt,
                                    'status': 'failed',
                                    'thumbnail_url': task.get('image_url', '')
                                }
                                add_video_to_db(video_data)
                                break
                        
                        time.sleep(3)
            except Exception as e:
                print(f"Error processing task: {e}")
        
        # Sleep before checking for new tasks
        time.sleep(5)
    
# Start the background worker thread
def start_background_worker():
    worker_thread = threading.Thread(target=process_queue_worker, daemon=True)
    worker_thread.start()

# Main application
def main():
    # Start the background worker if it's not already running
    if 'worker_started' not in st.session_state:
        start_background_worker()
        st.session_state.worker_started = True
    
    # Navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["Generate Video", "Gallery", "Queue Status"])
    
    # Use fixed bucket name
    bucket_name = os.getenv("GCS_BUCKET_NAME")  # .env bucket name
    
    if page == "Generate Video":
        generate_video_page(bucket_name)
    elif page == "Gallery":
        gallery_page()
    elif page == "Queue Status":
        queue_status_page()

def generate_video_page(bucket_name):
    st.title("AI Video Generator")
    st.write("Upload an image and provide a description to generate a professional video")
    
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
        st.subheader("Request Status")
        result_placeholder = st.empty()
    
    if generate_button and uploaded_file is not None and text_input:
        with st.spinner("Processing..."):
            # Generate unique task ID
            task_id = str(uuid.uuid4())
            file_extension = os.path.splitext(uploaded_file.name)[1]
            destination_blob_name = f"uploads/{task_id}{file_extension}"
            
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
                    
                    # Add task to queue instead of processing immediately
                    task = {
                        'id': task_id,
                        'timestamp': datetime.datetime.now().isoformat(),
                        'description': text_input,
                        'enhanced_prompt': enhanced_prompt,
                        'image_url': image_url,
                        'status': 'queued'
                    }
                    
                    if add_to_queue(task):
                        queue_position = get_queue_position(task_id)
                        st.success(f"Task added to queue at position {queue_position}")
                        
                        # Show queue information
                        result_placeholder.info(f"""
                        Your video generation request has been queued.
                        
                        Task ID: {task_id}
                        Queue Position: {queue_position}
                        
                        You can check the status in the Queue Status page.
                        Once completed, the video will appear in the Gallery.
                        """)
                    else:
                        st.error("Failed to add task to queue")
                else:
                    st.error("Failed to generate enhanced prompt")
            else:
                st.error("Failed to upload image")
    elif generate_button:
        if not uploaded_file:
            st.warning("Please upload an image")
        if not text_input:
            st.warning("Please enter a description")

def gallery_page():
    st.title("Video Gallery")
    st.write("Browse all generated videos")
    
    videos = load_videos_db()
    
    if not videos:
        st.info("No videos have been generated yet. Go to the Generate Video page to create some!")
        return
    
    # Sort videos by timestamp (newest first)
    videos.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    # Add filtering options
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Filter by status
        status_filter = st.selectbox(
            "Filter by status",
            ["All", "Completed", "Failed", "Processing"],
            index=0
        )
    
    with col2:
        # Search by description
        search_term = st.text_input("Search by description", "")
    
    with col3:
        # Sort options
        sort_option = st.selectbox(
            "Sort by",
            ["Newest first", "Oldest first"],
            index=0
        )
    
    # Apply filters
    filtered_videos = videos
    
    # Filter by status
    if status_filter != "All":
        filtered_videos = [v for v in filtered_videos if v.get('status', '').lower() == status_filter.lower()]
    
    # Filter by search term
    if search_term:
        filtered_videos = [v for v in filtered_videos if search_term.lower() in v.get('description', '').lower()]
    
    # Apply sorting
    if sort_option == "Oldest first":
        filtered_videos.reverse()
    
    # Pagination
    items_per_page = 6
    if 'gallery_page_num' not in st.session_state:
        st.session_state.gallery_page_num = 0
    
    total_pages = max(1, (len(filtered_videos) + items_per_page - 1) // items_per_page)
    
    # Page navigation
    col1, col2, col3 = st.columns([1, 3, 1])
    
    with col1:
        if st.button("← Previous", disabled=(st.session_state.gallery_page_num <= 0)):
            st.session_state.gallery_page_num -= 1
            st.experimental_rerun()
    
    with col2:
        st.write(f"Page {st.session_state.gallery_page_num + 1} of {total_pages}")
    
    with col3:
        if st.button("Next →", disabled=(st.session_state.gallery_page_num >= total_pages - 1)):
            st.session_state.gallery_page_num += 1
            st.experimental_rerun()
    
    # Get current page videos
    start_idx = st.session_state.gallery_page_num * items_per_page
    end_idx = min(start_idx + items_per_page, len(filtered_videos))
    current_page_videos = filtered_videos[start_idx:end_idx]
    
    # Display videos in a grid
    cols_per_row = 3
    
    if not current_page_videos:
        st.info("No videos match your filters. Try adjusting your search criteria.")
        return
    
    # Create rows of videos
    for i in range(0, len(current_page_videos), cols_per_row):
        row_videos = current_page_videos[i:i+cols_per_row]
        cols = st.columns(cols_per_row)
        
        for j, video in enumerate(row_videos):
            with cols[j]:
                # Display video card with a border
                with st.container():
                    st.markdown("""
                    <style>
                    .video-card {
                        border: 1px solid #ddd;
                        border-radius: 5px;
                        padding: 10px;
                        margin-bottom: 10px;
                    }
                    </style>
                    """, unsafe_allow_html=True)
                    
                    st.markdown('<div class="video-card">', unsafe_allow_html=True)
                    
                    # Display video card
                    st.subheader(video.get('description', 'Untitled')[:30] + "..." if len(video.get('description', 'Untitled')) > 30 else video.get('description', 'Untitled'))
                    
                    # Display status
                    status = video.get('status', 'unknown')
                    if status == 'completed':
                        st.success("Completed")
                        # Display video
                        st.video(video.get('video_url', ''))
                    elif status == 'failed':
                        st.error("Failed")
                        # Display thumbnail if available
                        if video.get('thumbnail_url'):
                            st.image(video.get('thumbnail_url'), use_column_width=True)
                    else:
                        st.warning("Processing")
                        # Display thumbnail if available
                        if video.get('thumbnail_url'):
                            st.image(video.get('thumbnail_url'), use_column_width=True)
                    
                    # Display timestamp
                    timestamp = video.get('timestamp', '')
                    if timestamp:
                        try:
                            dt = datetime.datetime.fromisoformat(timestamp)
                            st.caption(f"Created: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                        except:
                            st.caption(f"Created: {timestamp}")
                    
                    # Display details in expander
                    with st.expander("Details"):
                        st.write(f"ID: {video.get('id', 'N/A')}")
                        st.write(f"Status: {status}")
                        if video.get('prompt'):
                            st.text_area("Prompt", value=video.get('prompt'), height=100, disabled=True)
                    
                    st.markdown('</div>', unsafe_allow_html=True)

def queue_status_page():
    st.title("Queue Status")
    st.write("Check the status of your video generation requests")
    
    # Add auto-refresh option
    auto_refresh = st.checkbox("Auto-refresh (every 10 seconds)", value=False)
    if auto_refresh:
        st.markdown("""
        <meta http-equiv="refresh" content="10">
        """, unsafe_allow_html=True)
    
    # Manual refresh button
    if st.button("🔄 Refresh Now"):
        st.experimental_rerun()
    
    # Get current queue
    queue = load_queue()
    queue_list = list(queue)
    
    # Get completed/failed videos
    videos = load_videos_db()
    
    # Calculate estimated processing times
    avg_processing_time = 60  # Default: 1 minute per task
    
    # If we have completed videos, calculate average processing time
    completed_videos = [v for v in videos if v.get('status') == 'completed']
    if len(completed_videos) >= 2:
        try:
            # Calculate average time between timestamps
            processing_times = []
            for i in range(1, len(completed_videos)):
                end_time = datetime.datetime.fromisoformat(completed_videos[i-1].get('timestamp'))
                start_time = datetime.datetime.fromisoformat(completed_videos[i].get('timestamp'))
                delta = (end_time - start_time).total_seconds()
                if 0 < delta < 3600:  # Only consider reasonable times (0-1 hour)
                    processing_times.append(delta)
            
            if processing_times:
                avg_processing_time = sum(processing_times) / len(processing_times)
        except:
            pass  # Use default if calculation fails
    
    # Display queue metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Tasks in Queue", len(queue_list))
    with col2:
        if queue_list:
            est_wait = len(queue_list) * avg_processing_time
            if est_wait < 60:
                wait_str = f"{int(est_wait)} seconds"
            elif est_wait < 3600:
                wait_str = f"{int(est_wait/60)} minutes"
            else:
                wait_str = f"{est_wait/3600:.1f} hours"
            st.metric("Estimated Wait Time", wait_str)
        else:
            st.metric("Estimated Wait Time", "0 seconds")
    with col3:
        st.metric("Completed Videos", len([v for v in videos if v.get('status') == 'completed']))
    
    # Current Queue section
    st.subheader("Current Queue")
    if queue_list:
        # Add task cancellation functionality
        if st.session_state.get('show_cancel_options', False):
            if st.button("Hide Cancel Options"):
                st.session_state.show_cancel_options = False
                st.experimental_rerun()
        else:
            if st.button("Show Cancel Options"):
                st.session_state.show_cancel_options = True
                st.experimental_rerun()
        
        # Create a table of queued tasks
        queue_data = []
        for i, task in enumerate(queue_list):
            task_data = {
                "Position": i + 1,
                "Task ID": task.get('id', 'N/A')[:8] + "...",
                "Description": task.get('description', 'N/A')[:30] + "..." if len(task.get('description', 'N/A')) > 30 else task.get('description', 'N/A'),
                "Timestamp": task.get('timestamp', 'N/A')
            }
            
            # Add estimated time
            est_time = datetime.datetime.now() + datetime.timedelta(seconds=i * avg_processing_time)
            task_data["Est. Completion"] = est_time.strftime("%H:%M:%S")
            
            queue_data.append(task_data)
        
        # Display the table
        st.dataframe(queue_data)
        
        # Show cancel options if enabled
        if st.session_state.get('show_cancel_options', False):
            st.subheader("Cancel Task")
            task_to_cancel = st.selectbox(
                "Select task to cancel",
                options=[f"{i+1}: {t.get('description', 'N/A')[:30]}..." for i, t in enumerate(queue_list)]
            )
            
            if st.button("Cancel Selected Task", type="primary"):
                # Get the index from the selection
                idx = int(task_to_cancel.split(":")[0]) - 1
                
                # Remove the task from the queue
                queue = load_queue()
                queue_list = list(queue)
                if 0 <= idx < len(queue_list):
                    cancelled_task = queue_list.pop(idx)
                    
                    # Save the updated queue
                    new_queue = deque(queue_list)
                    if save_queue(new_queue):
                        st.success(f"Task '{cancelled_task.get('description', 'N/A')[:30]}...' has been cancelled")
                        
                        # Add to videos DB as cancelled
                        cancelled_data = {
                            'id': cancelled_task.get('id', 'N/A'),
                            'timestamp': datetime.datetime.now().isoformat(),
                            'description': cancelled_task.get('description', 'N/A'),
                            'prompt': cancelled_task.get('enhanced_prompt', 'N/A'),
                            'status': 'cancelled',
                            'thumbnail_url': cancelled_task.get('image_url', '')
                        }
                        add_video_to_db(cancelled_data)
                        
                        # Refresh the page
                        time.sleep(1)
                        st.experimental_rerun()
                    else:
                        st.error("Failed to cancel task")
    else:
        st.info("No tasks currently in queue")
    
    # Recently Processed section
    st.subheader("Recently Processed")
    if videos:
        # Sort by timestamp (newest first)
        videos.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # Add filter for status
        status_filter = st.multiselect(
            "Filter by status",
            options=["completed", "failed", "cancelled"],
            default=["completed", "failed", "cancelled"]
        )
        
        # Filter videos by status
        filtered_videos = [v for v in videos if v.get('status', '') in status_filter]
        
        # Show only the 15 most recent
        recent_videos = filtered_videos[:15]
        
        if recent_videos:
            # Create a table of recent videos
            recent_data = []
            for video in recent_videos:
                status = video.get('status', 'N/A')
                status_emoji = "✅" if status == "completed" else "❌" if status == "failed" else "🚫" if status == "cancelled" else "⏳"
                
                recent_data.append({
                    "Task ID": video.get('id', 'N/A')[:8] + "...",
                    "Description": video.get('description', 'N/A')[:30] + "..." if len(video.get('description', 'N/A')) > 30 else video.get('description', 'N/A'),
                    "Status": f"{status_emoji} {status.capitalize()}",
                    "Timestamp": video.get('timestamp', 'N/A')
                })
            
            st.dataframe(recent_data)
            
            # Add option to view details of a specific video
            selected_video_id = st.selectbox(
                "View details for:",
                options=["Select a video..."] + [f"{v.get('id', 'N/A')[:8]}... - {v.get('description', 'N/A')[:30]}..." for v in recent_videos]
            )
            
            if selected_video_id != "Select a video...":
                # Get the selected video ID
                video_id = selected_video_id.split(" - ")[0].replace("...", "")
                
                # Find the video
                selected_video = None
                for v in recent_videos:
                    if v.get('id', 'N/A').startswith(video_id):
                        selected_video = v
                        break
                
                if selected_video:
                    st.subheader("Video Details")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**ID:** {selected_video.get('id', 'N/A')}")
                        st.write(f"**Status:** {selected_video.get('status', 'N/A').capitalize()}")
                        st.write(f"**Created:** {selected_video.get('timestamp', 'N/A')}")
                        st.write(f"**Description:** {selected_video.get('description', 'N/A')}")
                    
                    with col2:
                        # Show video or thumbnail
                        if selected_video.get('status') == 'completed' and selected_video.get('video_url'):
                            st.video(selected_video.get('video_url'))
                        elif selected_video.get('thumbnail_url'):
                            st.image(selected_video.get('thumbnail_url'), use_column_width=True)
                    
                    # Show prompt
                    if selected_video.get('prompt'):
                        with st.expander("View Prompt"):
                            st.text_area("", value=selected_video.get('prompt'), height=200, disabled=True)
        else:
            st.info(f"No videos with status: {', '.join(status_filter)}")
    else:
        st.info("No videos have been processed yet")

if __name__ == "__main__":
    main()