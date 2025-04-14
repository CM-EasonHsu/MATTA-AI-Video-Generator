# pages/1_Pending_Approvals.py
import streamlit as st
from utils import (
    get_submissions_by_status,
    display_submission_item,
    STATUS_PENDING_PHOTO_APPROVAL,
    STATUS_PENDING_VIDEO_APPROVAL,
)
import time

st.set_page_config(page_title="Pending Approvals", page_icon="🛡️", layout="centered")
st.header("✅ Pending Approvals")
st.caption("Review uploaded photos or generated videos awaiting your decision.")

# Ensure session state for rejection dialog is initialized (might be needed if user lands here first)
if "confirmed_rejection" not in st.session_state:
    st.session_state.confirmed_rejection = False
if "reject_sub_id" not in st.session_state:
    st.session_state.reject_sub_id = None

mod_task = st.radio(
    "Select Moderation Task:",
    ("📸 Pending Photos", "🎬 Pending Videos"),
    key="pending_task_radio",
    horizontal=True,
    captions=["Review uploaded images.", "Review generated videos."],
)

st.divider()

if mod_task == "📸 Pending Photos":
    item_type = "photo"
    status_filter = STATUS_PENDING_PHOTO_APPROVAL
    header_text = "Pending Photo Approvals"
    fetch_spinner_text = "⏳ Fetching pending photos..."
    no_items_text = "👍 No photos currently awaiting approval."
else:  # mod_task == "🎬 Pending Videos":
    item_type = "video"
    status_filter = STATUS_PENDING_VIDEO_APPROVAL
    header_text = "Pending Video Approvals"
    fetch_spinner_text = "⏳ Fetching pending videos..."
    no_items_text = "👍 No videos currently awaiting approval."

st.subheader(header_text)
with st.spinner(fetch_spinner_text):
    # Fetch only the specific pending items
    pending_items = get_submissions_by_status(status=status_filter)

if not pending_items:
    st.info(no_items_text)
else:
    st.caption(f"Found {len(pending_items)} item(s) awaiting moderation.")
    # Display items using the shared function
    for item in pending_items:
        display_submission_item(item, item_type, include_approval=True)

    # Add a refresh button at the bottom
    if st.sidebar.button(":material/refresh: Refresh List", use_container_width=True):
        st.rerun()
