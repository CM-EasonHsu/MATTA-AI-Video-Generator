import streamlit as st
import requests
import os

import time  # For simulating delays or adding pauses if needed

# --- Configuration ---
# Get the backend API URL from environment variable set in docker-compose.yml
# Provide a default for local running outside docker if needed
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000")
if not BACKEND_API_URL:
    st.error("Error: BACKEND_API_URL environment variable not set.")
    st.stop()

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


def get_pending_items(item_type: str):
    """Fetches pending photos or videos for moderation."""
    endpoint = f"{BACKEND_API_URL}/moderation/pending_{item_type}"
    try:
        response = requests.get(endpoint, timeout=20)
        if response.status_code == 200:
            return response.json()
        else:
            handle_api_error(response, f"Failed to fetch pending {item_type}.")
            return []
    except requests.exceptions.RequestException as e:
        st.error(f"Network error fetching pending {item_type}: {e}")
        return []


def moderate_item(item_type: str, submission_id: str, decision: str):
    """Sends moderation decision (approve/reject) to the backend."""
    endpoint = f"{BACKEND_API_URL}/moderation/{item_type}/{submission_id}/action"
    payload = {"decision": decision}  # "approve" or "reject"
    try:
        response = requests.post(endpoint, json=payload, timeout=15)
        if response.status_code == 204:  # No Content Success
            st.success(f"Submission {submission_id} successfully {decision}d.")
            return True
        else:
            handle_api_error(response, f"Failed to {decision} submission {submission_id}.")
            return False
    except requests.exceptions.RequestException as e:
        st.error(f"Network error moderating {item_type} {submission_id}: {e}")
        return False


@st.dialog("Confirm Rejection")
def confirm_rejection_dialog(item_type_singular: str, sub_id: str):
    """Displays a confirmation dialog before rejecting an item."""
    st.warning(f"⚠️ Are you sure you want to reject this {item_type_singular} (Submission ID: `{sub_id}`)?")
    st.markdown("This action will mark the submission as rejected and cannot be easily undone.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Yes, Confirm Rejection", type="primary", use_container_width=True):
            st.session_state.confirmed_rejection = True
            st.rerun()
    with col2:
        if st.button("Cancel", use_container_width=True):
            st.session_state.confirmed_rejection = False
            st.rerun()


def render_moderation_page():
    """Renders the moderation interface."""
    st.header("🛡️ Moderation Console")

    mod_task = st.radio(
        "Select Moderation Task:",
        ("📸 Approve Photos", "🎬 Approve Videos"),
        horizontal=True,
        captions=["Review uploaded images.", "Review generated videos."],
    )

    st.divider()

    item_type = "photos" if mod_task == "📸 Approve Photos" else "videos"
    header_text = "Pending Photo Approvals" if item_type == "photos" else "Pending Video Approvals"
    fetch_spinner_text = f"⏳ Fetching pending {item_type}..."
    no_items_text = f"✅ No {item_type} currently awaiting approval."

    st.subheader(header_text)
    with st.spinner(fetch_spinner_text):
        # Use consistent item_type naming aligned with API calls
        pending_items = get_pending_items(item_type)

    if not pending_items:
        st.info(no_items_text)
        return

    st.caption(f"Found {len(pending_items)} item(s) awaiting moderation.")

    # --- Display loop ---
    for item in pending_items:
        sub_id = item.get("id")
        sub_code = item.get("submission_code")
        photo_url = item.get("photo_url")
        video_url = item.get("video_url")  # Will be None for photos
        created_at = item.get("created_at", "N/A")
        updated_at = item.get("updated_at", "N/A")  # More relevant for videos
        prompt = item.get("user_prompt", "").strip()

        with st.container(border=True):
            # --- Item Header ---
            st.markdown(f"**Submission ID:** `{sub_id}`")
            st.markdown(f"**Code:** `{sub_code}`")
            st.markdown(f"**Submitted:** {created_at}")
            if item_type == "videos":
                st.caption(f"Generated: {updated_at}")  # Show generation time for videos

            # --- User Prompt ---
            if prompt:
                with st.expander("📝 View User Prompt"):
                    st.text(prompt)
            else:
                st.caption("No user prompt provided.")

            # --- Content Display ---
            if item_type == "photos":
                if photo_url:
                    st.image(photo_url, caption="Uploaded Photo", use_container_width=True)  # Adjust width as needed
                else:
                    st.warning("⚠️ Photo URL missing.")
            elif item_type == "videos":
                col_media1, col_media2 = st.columns(2)
                with col_media1:
                    st.markdown("**Original Photo**")
                    if photo_url:
                        st.image(photo_url, use_container_width=True)
                    else:
                        st.warning("⚠️ Original photo URL missing.")
                with col_media2:
                    st.markdown("**Generated Video**")
                    if video_url:
                        st.video(video_url)
                    else:
                        st.warning("⚠️ Generated video URL missing.")

            # --- Action Buttons ---
            cols_buttons = st.columns(2)
            action_key_prefix = f"{item_type}_{sub_id}"  # Unique key prefix
            approve_label = "✅ Approve"
            reject_label = "❌ Reject"
            # Get singular form for dialog message ('photo' or 'video')
            item_type_singular = item_type[:-1]

            with cols_buttons[0]:
                if st.button(
                    approve_label, key=f"approve_{action_key_prefix}", type="primary", use_container_width=True
                ):
                    with st.spinner(f"Processing approval for {sub_id}..."):
                        success = moderate_item(item_type, sub_id, "approve")
                        if success:
                            st.toast(f"Approved {sub_id}!", icon="✅")
                            time.sleep(0.5)  # Allow toast to show
                            st.rerun()  # Refresh the list
            with cols_buttons[1]:
                if st.button(reject_label, key=f"reject_{action_key_prefix}", use_container_width=True):
                    confirm_rejection_dialog(item_type_singular, sub_id)

                # Only proceed if the dialog returned True (confirm button clicked)
                if st.session_state.get("confirmed_rejection", False):
                    with st.spinner(f"Processing rejection for {sub_id}..."):
                        success = moderate_item(item_type, sub_id, "reject")
                        if success:
                            st.toast(f"Rejected {sub_id}!", icon="❌")
                            time.sleep(0.5)
                            del st.session_state["confirmed_rejection"]
                            # Rerun the main page to refresh the list after successful rejection
                            st.rerun()


# --- Main App Logic ---

st.set_page_config(layout="centered", page_title="Moderation Console", page_icon="🛡️")

render_moderation_page()

# Initialize session state for tracking code if it doesn't exist
if "last_submission_code" not in st.session_state:
    st.session_state.last_submission_code = ""
