import streamlit as st
import requests
import os
import io
import time  # For simulating delays or adding pauses if needed

# --- Configuration ---
# Get the backend API URL from environment variable set in docker-compose.yml
# Provide a default for local running outside docker if needed
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000")
if not BACKEND_API_URL:
    st.error("Error: BACKEND_API_URL environment variable not set.")
    st.stop()

# --- API Client Functions ---


def handle_api_error(response, default_message="API Error"):
    """Helper to show user-friendly API errors."""
    try:
        detail = response.json().get("detail", default_message)
        if isinstance(detail, list) and len(detail) > 0 and isinstance(detail[0], dict):
            # Handle FastAPI validation errors nicely
            errors = [f"{err.get('loc', ['unknown'])[1]}: {err.get('msg', 'invalid')}" for err in detail]
            st.error(f"Error: {response.status_code} - {'; '.join(errors)}")
        else:
            st.error(f"Error: {response.status_code} - {detail}")
    except Exception:
        st.error(f"Error: {response.status_code} - {response.text[:200]}")  # Show raw beginning of error


def submit_photo(uploaded_file, prompt: str):
    """Sends photo and prompt to the backend API."""
    files_data = {"photo": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
    data = {"user_prompt": prompt if prompt else ""}
    try:
        response = requests.post(f"{BACKEND_API_URL}/submissions/", files=files_data, data=data, timeout=30)
        if response.status_code == 201:  # Created
            return response.json()
        else:
            handle_api_error(response, "Failed to submit photo.")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Network error submitting photo: {e}")
        return None


def check_status(submission_code: str):
    """Checks the status of a submission."""
    if not submission_code:
        st.warning("Please enter a submission code.")
        return None
    try:
        response = requests.get(f"{BACKEND_API_URL}/submissions/{submission_code}/status", timeout=15)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            st.error(f"Submission code '{submission_code}' not found.")
            return None
        else:
            handle_api_error(response, f"Failed to get status for '{submission_code}'.")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Network error checking status: {e}")
        return None


# --- Constants for Statuses (Good Practice) ---
STATUS_VIDEO_APPROVED = "VIDEO_APPROVED"
STATUS_GENERATION_FAILED = "GENERATION_FAILED"
STATUS_PHOTO_REJECTED = "PHOTO_REJECTED"
STATUS_VIDEO_REJECTED = "VIDEO_REJECTED"
STATUS_PENDING_PHOTO_APPROVAL = "PENDING_PHOTO_APPROVAL"
STATUS_PHOTO_APPROVED = "PHOTO_APPROVED"
STATUS_QUEUED_FOR_GENERATION = "QUEUED_FOR_GENERATION"
STATUS_GENERATING_VIDEO = "GENERATING_VIDEO"
STATUS_PENDING_VIDEO_APPROVAL = "PENDING_VIDEO_APPROVAL"

PROCESSING_STATUSES = [
    STATUS_PENDING_PHOTO_APPROVAL,
    STATUS_PHOTO_APPROVED,
    STATUS_QUEUED_FOR_GENERATION,
    STATUS_GENERATING_VIDEO,
    STATUS_PENDING_VIDEO_APPROVAL,
]


def render_user_page():
    """Renders the main page for user submissions and status checks."""
    st.header("✨AI Video Generator✨")
    st.markdown(
        "Turn your photos into short, dynamic videos! Upload a photo, optionally describe the desired effect, and let the AI work its magic."
    )

    # --- Submission Section ---
    st.subheader("1. Create Your Video")

    col1, col2 = st.columns([1, 2])  # Adjust ratio as needed

    with col1:
        uploaded_file = st.file_uploader(
            "Choose your photo:", type=["jpg", "jpeg", "png", "webp"], help="Upload the image you want to animate."
        )
        if uploaded_file is not None:
            st.image(uploaded_file, caption="Your Uploaded Photo", use_container_width=True)

    with col2:
        user_prompt = st.text_area(
            "Describe the video effect (Optional):",
            placeholder="e.g., 'Make the person wave', 'slow zoom in on the landscape', 'add a sparkle effect', 'vintage film style'",
            help="Tell the AI what kind of animation or style you'd like.",
            height=100,  # Adjust height
        )

        # Disable button if no file is uploaded
        submit_disabled = uploaded_file is None
        if st.button(
            ":material/movie: Generate Video", disabled=submit_disabled, type="primary", use_container_width=True
        ):
            if uploaded_file is not None:  # Redundant check due to disabled state, but safe
                with st.spinner("✨ Submitting your request... Please wait."):
                    result = submit_photo(uploaded_file, user_prompt)
                if result:
                    sub_code = result.get("submission_code")
                    st.success(f"✅ Submission successful! Your tracking code is ready.")
                    st.info("Use this code below to check the status of your video generation.")
                    st.code(sub_code)
                    # Store code in session state to prefill status check
                    st.session_state.last_submission_code = sub_code
            # No need for an else here because the button is disabled if no file
        # elif submit_disabled:
        #     st.warning("👈 Please upload a photo first.")

    st.divider()

    # --- Status Check Section ---
    st.subheader("2. Check Your Video Status")
    with st.expander("🔍 Enter your tracking code here", expanded=True):  # Start expanded
        # Pre-fill if we just submitted one
        code_to_check = st.text_input(
            "Tracking Code:",
            value=st.session_state.get("last_submission_code", ""),
            placeholder="Paste your tracking code",
        )

        if st.button(":material/search: Check Status", type="primary", use_container_width=True):
            if code_to_check:
                with st.spinner(f"⏳ Checking status for `{code_to_check}`..."):
                    status_info = check_status(code_to_check)

                if status_info:
                    # Use columns for better layout of status info
                    col_status1, col_status2 = st.columns(2)
                    with col_status1:
                        st.write(f"**Submission Code:**")
                        st.code(status_info.get("submission_code", "N/A"))
                    with col_status2:
                        st.write(f"**Last Updated:**")
                        st.caption(f"{status_info.get('updated_at', 'N/A')}")

                    status = status_info.get("status", "Unknown")
                    st.write("**Current Status:**")

                    if status == STATUS_VIDEO_APPROVED:
                        st.success(f"🎉 **Ready!** Your video has been generated and approved.")
                        video_url = status_info.get("video_url")
                        if video_url:
                            st.video(video_url)
                        else:
                            st.warning("Video URL is missing, although status is approved. Please contact support.")
                    elif status == STATUS_GENERATION_FAILED:
                        st.error(
                            f"❌ **Failed:** Video generation encountered an error. {status_info.get('error_message', 'No details provided.')}"
                        )
                    elif status in [STATUS_PHOTO_REJECTED, STATUS_VIDEO_REJECTED]:
                        st.error(
                            f"🚫 **Rejected:** Your submission could not be processed ({status}). This might be due to content policy or technical issues."
                        )
                    elif status in PROCESSING_STATUSES:
                        st.info(
                            f"⏳ **Processing:** Your submission is currently in progress (`{status}`). Please check back later."
                        )
                        # Future Enhancement: If backend provides progress %:
                        # progress_percent = status_info.get("progress", 0)
                        # st.progress(progress_percent / 100.0, text=f"Status: {status}")
                    else:
                        st.warning(
                            f"❓ **Unknown Status:** Received status '{status}'. Please check again later or contact support if this persists."
                        )
            else:
                st.warning("Please enter a submission code to check.")


# --- Main App Logic ---
st.set_page_config(layout="wide", page_title="AI Video Generator", page_icon="🎥")

render_user_page()

# Initialize session state for tracking code if it doesn't exist
if "last_submission_code" not in st.session_state:
    st.session_state.last_submission_code = ""
