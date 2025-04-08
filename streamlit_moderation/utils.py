# utils.py
import streamlit as st
import requests
import os
import time

# --- Configuration ---
# Get the backend API URL from environment variable set in docker-compose.yml
# Provide a default for local running outside docker if needed
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000")
if not BACKEND_API_URL:
    st.error("CRITICAL ERROR: BACKEND_API_URL environment variable not set.")
    st.stop()  # Stop execution if the backend URL isn't configured

# --- Constants for Statuses ---
STATUS_PENDING_PHOTO_APPROVAL = "PENDING_PHOTO_APPROVAL"
STATUS_PHOTO_APPROVED = "PHOTO_APPROVED"
STATUS_PHOTO_REJECTED = "PHOTO_REJECTED"
STATUS_QUEUED_FOR_GENERATION = "QUEUED_FOR_GENERATION"
STATUS_GENERATING_VIDEO = "GENERATING_VIDEO"
STATUS_GENERATION_FAILED = "GENERATION_FAILED"
STATUS_PENDING_VIDEO_APPROVAL = "PENDING_VIDEO_APPROVAL"
STATUS_VIDEO_APPROVED = "VIDEO_APPROVED"
STATUS_VIDEO_REJECTED = "VIDEO_REJECTED"

ALL_STATUSES = [
    STATUS_PENDING_PHOTO_APPROVAL,
    STATUS_PHOTO_APPROVED,
    STATUS_PHOTO_REJECTED,
    STATUS_QUEUED_FOR_GENERATION,
    STATUS_GENERATING_VIDEO,
    STATUS_GENERATION_FAILED,
    STATUS_PENDING_VIDEO_APPROVAL,
    STATUS_VIDEO_APPROVED,
    STATUS_VIDEO_REJECTED,
]

# --- API Client Functions ---


def handle_api_error(response, default_message="API Error"):
    """Helper to show user-friendly API errors."""
    try:
        detail = response.json().get("detail", default_message)
        if isinstance(detail, list) and len(detail) > 0 and isinstance(detail[0], dict):
            errors = [f"{err.get('loc', ['unknown'])[1]}: {err.get('msg', 'invalid')}" for err in detail]
            st.error(f"Error: {response.status_code} - {'; '.join(errors)}")
        else:
            st.error(f"Error: {response.status_code} - {detail}")
    except Exception:
        st.error(f"Error: {response.status_code} - {response.text[:200]}")


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


def get_submissions_by_status(status: str):
    """Fetches submissions based on their status."""
    endpoint = f"{BACKEND_API_URL}/submissions"
    params = {"status": status}
    try:
        response = requests.get(endpoint, params=params, timeout=30)  # Increased timeout slightly
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404 and status:  # Handle case where no items exist for a status
            return []  # Return empty list, not an error
        else:
            handle_api_error(response, f"Failed to fetch submissions with status '{status}'.")
            return []
    except requests.exceptions.RequestException as e:
        st.error(f"Network error fetching submissions for status '{status}': {e}")
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


def retry_generation(submission_id: str):
    """Sends a request to retry video generation for a failed submission."""
    endpoint = f"{BACKEND_API_URL}/moderation/retry_generation/{submission_id}"
    try:
        response = requests.post(endpoint, timeout=15)
        if response.status_code == 200:  # Assuming 200 OK for retry success
            st.success(f"Retrying generation for submission {submission_id}.")
            return True
        else:
            handle_api_error(response, f"Failed to retry generation for {submission_id}.")
            return False
    except requests.exceptions.RequestException as e:
        st.error(f"Network error retrying generation for {submission_id}: {e}")
        return False


@st.dialog("Confirm Rejection")
def confirm_rejection_dialog(item_type_singular: str, sub_id: str):
    """Displays a confirmation dialog before rejecting an item."""
    st.warning(f"⚠️ Are you sure you want to reject this {item_type_singular} (Submission ID: `{sub_id}`)?")
    st.markdown("This action will mark the submission as rejected and may not be easily undone.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Yes, Confirm Rejection", type="primary", use_container_width=True):
            st.session_state.confirmed_rejection = True
            st.session_state.reject_sub_id = sub_id  # Store which ID is being rejected
            st.rerun()
    with col2:
        if st.button("Cancel", use_container_width=True):
            st.session_state.confirmed_rejection = False
            st.session_state.reject_sub_id = None
            st.rerun()


def display_submission_item(item, active_status_filter=None):
    """Renders a single submission item in a consistent format."""
    sub_id = item.get("id")
    sub_code = item.get("submission_code")
    photo_url = item.get("photo_url")
    video_url = item.get("video_url")
    created_at = item.get("created_at", "N/A")
    updated_at = item.get("updated_at", "N/A")
    prompt = item.get("user_prompt", "").strip()
    current_status = item.get("status")  # Get the actual status from the item data

    # Determine item type based on status (heuristic, adjust if backend provides type explicitly)
    item_type = (
        "videos"
        if "VIDEO" in current_status or "GENERATION" in current_status or current_status == STATUS_QUEUED_FOR_GENERATION
        else "photos"
    )
    item_type_singular = "video" if item_type == "videos" else "photo"

    with st.container(border=True):
        # --- Item Header ---
        st.markdown(f"**Submission ID:** `{sub_id}`")
        if sub_code:
            st.markdown(f"**Code:** `{sub_code}`")
        st.markdown(f"**Status:** `{current_status}`")
        st.markdown(f"**Submitted:** {created_at}")
        if updated_at != created_at:  # Show updated time if different
            st.markdown(f"**Last Updated:** {updated_at}")

        # --- User Prompt ---
        if prompt:
            with st.expander("📝 View User Prompt"):
                st.text_area(
                    "Prompt", prompt, height=100, key=f"prompt_{sub_id}", disabled=True
                )  # Use text_area for better wrapping
        else:
            st.caption("No user prompt provided.")

        # --- Content Display ---
        if item_type == "photos":
            if photo_url:
                st.image(photo_url, caption="Uploaded Photo", use_container_width=True)
            else:
                st.warning("⚠️ Photo URL missing.")
        elif item_type == "videos":
            # Display photo and video side-by-side if both exist
            if photo_url and video_url:
                col_media1, col_media2 = st.columns(2)
                with col_media1:
                    st.markdown("**Original Photo**")
                    st.image(photo_url, use_container_width=True)
                with col_media2:
                    st.markdown("**Generated Video**")
                    st.video(video_url)
            # Display only photo if video doesn't exist (e.g., pending generation, failed)
            elif photo_url:
                st.markdown("**Original Photo**")
                st.image(photo_url, caption="Photo for Video Generation", use_container_width=True)
                if current_status not in [STATUS_PENDING_VIDEO_APPROVAL, STATUS_VIDEO_APPROVED, STATUS_VIDEO_REJECTED]:
                    st.caption("(Video not available for current status)")
            # Display only video if photo url is somehow missing but video exists
            elif video_url:
                st.markdown("**Generated Video**")
                st.video(video_url)
                st.warning("⚠️ Original Photo URL missing.")
            else:
                st.warning("⚠️ Neither Photo nor Video URL available.")

        # --- Action Buttons ---
        action_key_prefix = f"{item_type}_{sub_id}"  # Unique key prefix

        # --- Approval/Rejection Actions ---
        if current_status in [STATUS_PENDING_PHOTO_APPROVAL, STATUS_PENDING_VIDEO_APPROVAL]:
            cols_buttons = st.columns(2)
            approve_label = f"✅ Approve {item_type_singular.capitalize()}"
            reject_label = f"❌ Reject {item_type_singular.capitalize()}"

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
                    # Trigger the dialog
                    confirm_rejection_dialog(item_type_singular, sub_id)

                # Check if the confirmation came back for *this specific item*
                if (
                    st.session_state.get("confirmed_rejection", False)
                    and st.session_state.get("reject_sub_id") == sub_id
                ):
                    with st.spinner(f"Processing rejection for {sub_id}..."):
                        success = moderate_item(item_type, sub_id, "reject")
                        if success:
                            st.toast(f"Rejected {sub_id}!", icon="❌")
                            time.sleep(0.5)
                            # Clean up session state flags for this rejection
                            st.session_state.confirmed_rejection = False
                            st.session_state.reject_sub_id = None
                            st.rerun()
                        else:  # If API call fails, reset state to allow retry without re-confirm
                            st.session_state.confirmed_rejection = False
                            st.session_state.reject_sub_id = None
                            # No rerun here, error is already shown by moderate_item

        # --- Retry Action ---
        elif current_status == STATUS_GENERATION_FAILED:
            if st.button(f"🔄 Retry Generation", key=f"retry_{action_key_prefix}", use_container_width=True):
                with st.spinner(f"Requesting retry for {sub_id}..."):
                    success = retry_generation(sub_id)
                    if success:
                        st.toast(f"Retry requested for {sub_id}.", icon="🔄")
                        time.sleep(0.5)
                        st.rerun()

        # No actions needed for other statuses (Approved, Rejected, Queued etc.)
        # Add other actions here if needed in the future

        st.markdown("---")  # Visual separator inside the container
