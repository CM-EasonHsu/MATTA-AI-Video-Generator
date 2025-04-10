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


# --- Updated Function ---
def get_submissions_by_status(status: str, skip: int = 0, limit: int = 10):
    """
    Fetches a paginated list of submissions based on their status.

    Args:
        status (str): The status to filter submissions by.
        skip (int): The number of submissions to skip (for pagination).
        limit (int): The maximum number of submissions to return (page size).

    Returns:
        list: A list of submission dictionaries, or an empty list on error or if none found.
    """
    endpoint = f"{BACKEND_API_URL}/submissions"
    params = {"status": status, "skip": skip, "limit": limit}
    try:
        # Increased timeout slightly, adjust as needed
        response = requests.get(endpoint, params=params, timeout=30)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        return response.json()
    except requests.exceptions.HTTPError as e:
        # Handle 404 specifically: it means no items for this page/status, which isn't necessarily a server error
        if e.response.status_code == 404:
            # If skip > 0, it might just be an empty page beyond the last item.
            # If skip == 0, it means no items exist for this status at all.
            st.warning(f"No submissions found for status '{status}' on this page.")
            return []
        else:
            handle_api_error(
                e.response, f"Failed to fetch submissions for status '{status}' (page offset {skip}, limit {limit})."
            )
            return []
    except requests.exceptions.RequestException as e:
        st.error(f"Network error fetching submissions for status '{status}': {e}")
        return []
    except Exception as e:  # Catch other potential errors like JSONDecodeError
        st.error(f"An unexpected error occurred while fetching submissions: {e}")
        return []


# --- New Function ---
def get_submissions_count_by_status(status: str) -> int:
    """
    Fetches the total count of submissions for a given status.

    Args:
        status (str): The status to count submissions for.

    Returns:
        int: The total number of submissions, or 0 if none found or an error occurs.
    """
    # IMPORTANT: This assumes your backend has an endpoint like `/submissions/count`
    # or that the main `/submissions` endpoint can return a count when limit=0,
    # or includes the total count in its response headers or body along with items.
    # Adjust the endpoint and logic based on your actual backend API design.

    # --- Option 1: Dedicated Count Endpoint (Preferred) ---
    # endpoint = f"{BACKEND_API_URL}/submissions/count"
    # params = {"status": status}

    # --- Option 2: Using main endpoint with limit=0 (If supported) ---
    # endpoint = f"{BACKEND_API_URL}/submissions"
    # params = {"status": status, "limit": 0} # Ask API just for count

    # --- Option 3: Check response header/body from regular call (Adapt get_submissions_by_status if needed) ---
    # This example assumes a dedicated count endpoint.
    endpoint = f"{BACKEND_API_URL}/submissions/count"  # Replace with your actual count endpoint
    params = {"status": status}

    try:
        response = requests.get(endpoint, params=params, timeout=15)
        response.raise_for_status()
        # Assuming the endpoint returns JSON like: {"count": 123}
        data = response.json()
        if isinstance(data, dict) and "count" in data and isinstance(data["count"], int):
            return data["count"]
        else:
            # Fallback if response format is unexpected (e.g., just returns the number directly)
            try:
                return int(data)
            except (ValueError, TypeError):
                st.error(f"Unexpected format received from count endpoint for status '{status}': {data}")
                return 0

    except requests.exceptions.HTTPError as e:
        # A 404 here likely means 0 items match the status
        if e.response.status_code == 404:
            return 0
        else:
            handle_api_error(e.response, f"Failed to fetch submission count for status '{status}'.")
            return 0  # Return 0 on error to prevent pagination issues
    except requests.exceptions.RequestException as e:
        st.error(f"Network error fetching submission count for status '{status}': {e}")
        return 0
    except Exception as e:
        st.error(f"An unexpected error occurred while fetching count: {e}")
        return 0


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


def display_submission_item(item, item_type="photo", include_approval=False, include_retry=False):
    """Renders a single submission item in a consistent format."""
    sub_id = item.get("id")
    sub_code = item.get("submission_code")
    photo_url = item.get("photo_url")
    video_url = item.get("video_url")
    created_at = item.get("created_at", "N/A")
    updated_at = item.get("updated_at", "N/A")
    prompt = item.get("user_prompt", "").strip()
    current_status = item.get("status")

    if not photo_url:
        return None

    with st.container(border=True):
        col_1, col_2 = st.columns([1, 2])
        # --- Photo Display ---
        with col_1:
            st.image(photo_url, caption=f"Prompt: {prompt}", use_container_width=True)

        # --- Metadata ---
        with col_2:
            st.markdown(f"**Submission ID:** `{sub_id}`")
            if sub_code:
                st.markdown(f"**Code:** `{sub_code}`")
            # st.markdown(f"**Status:** `{current_status}`")
            st.markdown(f"**Submitted:** {created_at}")
            if updated_at != created_at:  # Show updated time if different
                st.markdown(f"**Last Updated:** {updated_at}")

        # --- Video ---
        if video_url:
            # st.markdown("**Generated Video**")
            # st.divider()
            st.video(video_url)

        # --- Action Buttons ---
        if include_approval:
            action_key_prefix = f"{item_type}_{sub_id}"  # Unique key prefix

            # --- Approval/Rejection Actions ---
            if current_status in [STATUS_PENDING_PHOTO_APPROVAL, STATUS_PENDING_VIDEO_APPROVAL]:
                cols_buttons = st.columns(2)
                approve_label = f"✅ Approve {item_type.capitalize()}"
                reject_label = f"❌ Reject {item_type.capitalize()}"

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
                        confirm_rejection_dialog(item_type, sub_id)

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

            if include_retry:
                # --- Retry Action ---
                if st.button(f"🔄 Retry Generation", key=f"retry_{action_key_prefix}", use_container_width=True):
                    with st.spinner(f"Requesting retry for {sub_id}..."):
                        success = retry_generation(sub_id)
                        if success:
                            st.toast(f"Retry requested for {sub_id}.", icon="🔄")
                            time.sleep(0.5)
                            st.rerun()
