# utils.py
import streamlit as st
import requests
import os
import time

from datetime import datetime
from pytz import timezone

# --- Configuration ---
# Get the backend API URL from environment variable set in docker-compose.yml
# Provide a default for local running outside docker if needed
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000")
API_KEY = os.getenv("BACKEND_API_KEY")
headers = {"X-API-KEY": API_KEY}

# --- Constants for Statuses ---
STATUS_PENDING_PHOTO_APPROVAL = "PENDING_PHOTO_APPROVAL"
STATUS_PHOTO_APPROVED = "PHOTO_APPROVED"
STATUS_PHOTO_REJECTED = "PHOTO_REJECTED"
STATUS_GENERATING_VIDEO = "GENERATING_VIDEO"
STATUS_GENERATION_FAILED = "GENERATION_FAILED"
STATUS_PENDING_VIDEO_APPROVAL = "PENDING_VIDEO_APPROVAL"
STATUS_VIDEO_APPROVED = "VIDEO_APPROVED"
STATUS_VIDEO_REJECTED = "VIDEO_REJECTED"

ALL_STATUSES = [
    STATUS_PENDING_PHOTO_APPROVAL,
    STATUS_PHOTO_APPROVED,
    STATUS_PHOTO_REJECTED,
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


def get_submission_by_code(submission_code: str):
    """Fetches a submission by its user-facing code."""
    endpoint = f"{BACKEND_API_URL}/submissions/{submission_code}"
    try:
        response = requests.get(endpoint, timeout=20, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            handle_api_error(response, f"Failed to fetch submission by code {submission_code}.")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Network error fetching submission by code {submission_code}: {e}")
        return None


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
        response = requests.get(endpoint, params=params, timeout=30, headers=headers)
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


def get_submissions_count_by_status(status: str) -> int:
    """
    Fetches the total count of submissions for a given status.

    Args:
        status (str): The status to count submissions for.

    Returns:
        int: The total number of submissions, or 0 if none found or an error occurs.
    """
    endpoint = f"{BACKEND_API_URL}/submissions/stats/count"  # Replace with your actual count endpoint
    params = {"status": status}

    try:
        response = requests.get(endpoint, params=params, timeout=15, headers=headers)
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


def moderate_item(item_type: str, submission_id: str, decision: str, reason=None):
    """Sends moderation decision (approve/reject) to the backend."""
    endpoint = f"{BACKEND_API_URL}/moderation/{item_type}/{submission_id}/action"
    payload = {"decision": decision, "reason": reason}  # "approve" or "reject"
    try:
        response = requests.post(endpoint, json=payload, timeout=15, headers=headers)
        if response.status_code == 204:  # No Content Success
            st.success(f"Submission {submission_id} successfully {decision}d.")
            return True
        else:
            handle_api_error(response, f"Failed to {decision} submission {submission_id}.")
            return False
    except requests.exceptions.RequestException as e:
        st.error(f"Network error moderating {item_type} {submission_id}: {e}")
        return False


def retry_item(submission_id: str, new_prompt: str):
    """Sends retry request to the backend."""
    endpoint = f"{BACKEND_API_URL}/moderation/photo/{submission_id}/retry"
    payload = {"prompt": new_prompt}
    try:
        response = requests.post(endpoint, json=payload, timeout=15, headers=headers)
        if response.status_code == 204:  # No Content Success
            st.success(f"Submission {submission_id} successfully retried.")
            return True
        else:
            handle_api_error(response, f"Failed to retry submission {submission_id}.")
            return False
    except requests.exceptions.RequestException as e:
        st.error(f"Network error retrying {submission_id}: {e}")
        return False


@st.dialog("Confirm Rejection")
def confirm_rejection_dialog(item_type_singular: str, sub_id: str):
    """Displays a confirmation dialog before rejecting an item."""
    st.warning(f"⚠️ Are you sure you want to reject this {item_type_singular} (Submission ID: `{sub_id}`)?")
    st.markdown("This action will mark the submission as rejected and may not be easily undone.")
    reason = st.text_input("Reason for rejection:", key="rejection_reason")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Yes, Confirm Rejection", type="primary", use_container_width=True, disabled=not reason):
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
    user_name = item.get("user_name", "N/A")
    email = item.get("email", "N/A")
    photo_url = item.get("photo_url")
    video_url = item.get("video_url")
    created_at = item.get("created_at")
    if created_at:
        created_at = (
            datetime.fromisoformat(created_at).astimezone(timezone("Asia/Singapore")).strftime("%Y-%m-%d %H:%M:%S")
        )

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
            # st.markdown(f"**Submission ID:** `{sub_id}`")
            st.markdown(f"**Code:** `{sub_code}`")
            st.markdown(f"**Name:** {user_name}")
            st.markdown(f"**Email:** {email}")
            st.markdown(f"**Status:** `{current_status}`")
            st.markdown(f"**Submitted:** {created_at}")

        # --- Video ---
        if video_url:
            # st.markdown("**Generated Video**")
            # st.divider()
            st.video(video_url)

        # --- Approval Buttons ---
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
                            success = moderate_item(
                                item_type, sub_id, "reject", reason=st.session_state.get("rejection_reason")
                            )
                            if success:
                                st.toast(f"Rejected {sub_id}!", icon="❌")
                                time.sleep(0.5)
                                # Clean up session state flags for this rejection
                                st.session_state.confirmed_rejection = False
                                st.session_state.reject_sub_id = None
                                st.session_state.rejection_reason = None
                                st.rerun()
                            else:  # If API call fails, reset state to allow retry without re-confirm
                                st.session_state.confirmed_rejection = False
                                st.session_state.reject_sub_id = None
                                st.session_state.rejection_reason = None
                                # No rerun here, error is already shown by moderate_item

        # --- Retry Action ---
        if include_retry:
            action_key_prefix = f"{item_type}_{sub_id}"  # Unique key prefix
            new_prompt = st.text_input("Retry with a different prompt:", value=prompt, key=f"edit_{action_key_prefix}")
            if st.button(
                f":material/replay: Retry", key=f"retry_{action_key_prefix}", use_container_width=True, type="primary"
            ):
                with st.spinner(f"Requesting retry for {sub_id}..."):
                    success = retry_item(submission_id=sub_id, new_prompt=new_prompt)
                    if success:
                        st.toast(f"Retry requested for {sub_id}.", icon="🔄")
                        time.sleep(0.5)
                        st.rerun()
