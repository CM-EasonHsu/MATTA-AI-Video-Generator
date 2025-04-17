import streamlit as st
import requests
import os

from datetime import datetime
from pytz import timezone

from utils import generate_prompt_suggestions

from streamlit.logger import get_logger

logger = get_logger(__name__)

# --- Configuration ---
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000")
API_KEY = os.getenv("BACKEND_API_KEY")
headers = {"X-API-KEY": API_KEY}
DEFAULT_VIDEO_PROMPT = "Animate this photo to create a scene filled with a relaxing and happy atmosphere."


def process_image():
    uploaded_file = st.session_state.get("photo_uploader")
    if uploaded_file:
        try:
            prompts = generate_prompt_suggestions(uploaded_file.read(), uploaded_file.type)
            st.session_state.prompt_suggestions = prompts
        except Exception as e:
            logger.error(f"Error generating prompt suggestions: {e}")
            st.session_state.prompt_suggestions = []


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


def submit_photo(uploaded_file, prompt: str, user_name: str, email: str):
    """Sends photo and prompt to the backend API."""
    files_data = {"photo": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
    data = {"user_prompt": prompt if prompt else DEFAULT_VIDEO_PROMPT, "user_name": user_name, "email": email}
    try:
        response = requests.post(
            f"{BACKEND_API_URL}/submissions/", files=files_data, data=data, timeout=30, headers=headers
        )
        if response.status_code == 201:
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
        response = requests.get(f"{BACKEND_API_URL}/submissions/{submission_code}", timeout=15, headers=headers)
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
STATUS_GENERATING_VIDEO = "GENERATING_VIDEO"
STATUS_PENDING_VIDEO_APPROVAL = "PENDING_VIDEO_APPROVAL"
STATUS_PENDING_GENERATION_RETRY = "PENDING_GENERATION_RETRY"

PROCESSING_STATUSES = [
    STATUS_PENDING_PHOTO_APPROVAL,
    STATUS_PHOTO_APPROVED,
    STATUS_GENERATING_VIDEO,
    STATUS_PENDING_VIDEO_APPROVAL,
    STATUS_PENDING_GENERATION_RETRY,
]


def render_user_page():
    """Renders the main page for user submissions and status checks,
    including email and consent fields."""
    st.header("✨AI Video Generator✨")
    st.markdown(
        "Turn your travel photos into short, dynamic videos! Upload a photo, describe the desired effect and let the AI work its magic."
    )

    # Initialize session state for submission code if not present
    if "last_submission_code" not in st.session_state:
        st.session_state.last_submission_code = ""

    # --- Submission Section ---
    st.subheader("1. Create Your Video")

    col1, col2 = st.columns([1, 2])  # Adjust ratio as needed

    with col1:
        uploaded_file = st.file_uploader(
            "Upload your travel photo here. (Photos containing children are not permitted):",
            type=["jpg", "jpeg", "png", "heic"],
            help="Upload the photo you want to animate.",
            key="photo_uploader",
            on_change=process_image,
        )
        if uploaded_file is not None:
            st.image(uploaded_file, caption="Your Uploaded Photo", use_container_width=True)
        else:
            # Add a placeholder or instruction if no file is uploaded yet
            st.info("👆 Upload your photo here to get started.")

    with col2:
        if st.session_state.get("prompt_suggestions"):
            selected_prompt = st.radio("Some ideas to help you get started:", st.session_state.prompt_suggestions)
            user_prompt = st.text_area(
                "Video description (Optional):",
                value=selected_prompt,
                help="Tell the AI what kind of animation or style you'd like.",
                height=100,
            )
        else:
            user_prompt = st.text_area(
                "Video description (Optional):",
                placeholder="e.g., 'Make the person wave', 'slow zoom in on the landscape', 'add a sparkle effect', 'vintage film style'",
                help="Tell the AI what kind of animation or style you'd like.",
                height=100,
            )

        user_name = st.text_input(
            "Your Name:",
            placeholder="Enter your name",
            key="user_name_input",
        )

        user_email = st.text_input(
            "Your Email Address:",
            placeholder="Enter your email address",
            key="user_email_input",
        )

        with st.expander(":material/docs: Terms of Service", expanded=False):
            disclaimer = (
                "* By uploading photos to generate video content using Veo 2, users must ensure that all images comply with applicable data protection regulations and community guidelines. Do not upload content that violates privacy rights or includes unauthorised personal data. \n"
                "* AI-generated content may not accurately represent real people, events or factual information. Users are advised to exercise discretion and independently verify any critical details. \n"
                "* By using this service, you confirm that you have read, understood, and accepted the terms and conditions and privacy policy in their entirety. If you do not agree with any part of these agreements, you are not authorized to use this service. \n"
                "* By providing your contact information, you consent to receive marketing promotions, updates, and offers via email, SMS, or other channels. You can opt-out at any time by following the unsubscribe instructions or contacting us directly. \n"
                "* By uploading or submitting your photo, you consent to the use of artificial intelligence (AI) technology to convert your photo into a video format. This process may involve automated analysis and transformation of your image to generate a video. You acknowledge that the result may be shared or processed according to the service's terms."
            )
            st.markdown(disclaimer)
        consent_given = st.checkbox(
            "I consent to the processing of my uploaded photo and information according to the terms of service.",
            key="consent_checkbox",
        )

        submit_disabled = not (uploaded_file and user_name and user_email and consent_given)

        if st.button(
            ":material/movie: Generate Video", disabled=submit_disabled, type="primary", use_container_width=True
        ):
            # Double-check conditions on click (though disabled state should prevent this)
            if uploaded_file is not None and consent_given:
                name_to_submit = st.session_state.get("user_name_input", "").strip()
                email_to_submit = st.session_state.get("user_email_input", "").strip()

                with st.spinner("✨ Submitting your request... Please wait."):
                    result = submit_photo(uploaded_file, user_prompt, name_to_submit, email_to_submit)

                if result and isinstance(result, dict):  # Check if result is a dictionary
                    sub_code = result.get("submission_code")
                    if sub_code:
                        st.success(f"✅ Submission successful! Your tracking code is ready.")
                        st.info("Use this code below to check the status of your video generation.")
                        st.code(sub_code)
                        # Store code in session state to prefill status check
                        st.session_state.last_submission_code = sub_code

                    else:
                        st.error("Submission failed. Backend did not return a submission code.")
                else:
                    st.error("Submission failed. Please try again later.")
            else:
                # This part should ideally not be reached if button is correctly disabled
                if not uploaded_file:
                    st.warning("👈 Please upload a photo first.")
                elif not consent_given:
                    st.warning("👈 Please check the consent box to proceed.")

        # Provide feedback if the button is disabled
        elif submit_disabled:
            if not uploaded_file:
                st.warning("👈 Please upload a photo first.")
            elif not consent_given:
                st.warning("👈 Please check the consent box to proceed.")

    st.divider()

    # --- Status Check Section ---
    st.subheader("2. Check Your Video Status")
    with st.expander("🔍 Enter your tracking code here", expanded=True):  # Start expanded
        # Pre-fill if we just submitted one
        code_to_check = st.text_input(
            "Tracking Code:",
            value=st.session_state.get("last_submission_code", ""),  # Use .get for safety
            placeholder="Paste your tracking code",
            key="tracking_code_input",  # Give it a key
        )

        if st.button(":material/search: Check Status", type="primary", use_container_width=True):
            if code_to_check:
                with st.spinner(f"⏳ Checking status for `{code_to_check}`..."):
                    status_info = check_status(code_to_check)

                if status_info and isinstance(status_info, dict):  # Check if status_info is valid
                    # Use columns for better layout of status info
                    col_status1, col_status2 = st.columns(2)
                    with col_status1:
                        st.write(f"**Submission Code:**")
                        st.code(status_info.get("submission_code", "N/A"))
                    with col_status2:

                        updated_at = status_info.get("updated_at")
                        if updated_at:
                            st.write(f"**Last Updated:**")
                            last_updated_str = (
                                datetime.fromisoformat(updated_at)
                                .astimezone(timezone("Asia/Singapore"))
                                .strftime("%Y-%m-%d %H:%M:%S")
                            )
                            st.caption(f"{last_updated_str}")

                    status = status_info.get("status", "Unknown")
                    st.write("**Current Status:**")

                    if status == STATUS_VIDEO_APPROVED:
                        st.success(f"🎉 **Ready!** Your video has been generated and approved.")
                        video_url = status_info.get("video_url")
                        if video_url:
                            st.video(video_url)
                        else:
                            st.warning("Video URL is missing. Please try again with another photo.")
                    elif status == STATUS_GENERATION_FAILED:
                        st.error(
                            f"❌ **Failed:** Video generation encountered an error. Please try again with another photo."
                        )
                    elif status in [STATUS_PHOTO_REJECTED, STATUS_VIDEO_REJECTED]:
                        if status_info.get("comment"):
                            st.error(
                                f"🚫 **Rejected:** Your submission could not be processed ({status}). Reason: {status_info.get('comment')}. Please try again with another photo."
                            )
                        else:
                            st.error(
                                f"🚫 **Rejected:** Your submission could not be processed ({status}). This might be due to content policy or technical issues. Please try again with another photo."
                            )
                    elif status in PROCESSING_STATUSES:
                        st.info(
                            f"⏳ **Processing:** Your submission is currently in progress (`{status}`). Please check back later."
                        )
                    else:
                        st.warning(
                            f"❓ **Unknown Status:** Received status '{status}'. Please check again later or try again with another photo."
                        )
                elif status_info is None:
                    st.error(f"❌ Code `{code_to_check}` not found. Please check the code and try again.")
                else:
                    st.error("Received invalid status information from the server.")
            else:
                st.warning("Please enter a submission code to check.")


# --- Main App Logic ---
st.set_page_config(layout="wide", page_title="AI Video Generator", page_icon="✨")

render_user_page()

# Initialize session state for tracking code if it doesn't exist
if "last_submission_code" not in st.session_state:
    st.session_state.last_submission_code = ""
