# pages/2_View_by_Status.py
import streamlit as st
from utils import get_submissions_by_status, display_submission_item, ALL_STATUSES
import time

st.header("📊 View Submissions by Status")
st.caption("Browse submissions based on their current processing status.")

# Ensure session state for rejection dialog is initialized
if "confirmed_rejection" not in st.session_state:
    st.session_state.confirmed_rejection = False
if "reject_sub_id" not in st.session_state:
    st.session_state.reject_sub_id = None

# Dropdown to select status
selected_status = st.selectbox(
    "Select Status to View:",
    options=ALL_STATUSES,
    index=None,  # Default to showing nothing until selected
    placeholder="Choose a status...",
)

st.divider()

if selected_status:
    st.subheader(f"Submissions with Status: `{selected_status}`")
    with st.spinner(f"⏳ Fetching submissions with status '{selected_status}'..."):
        submissions = get_submissions_by_status(selected_status)

    if not submissions:
        st.info(f"✅ No submissions found with the status '{selected_status}'.")
    else:
        st.caption(f"Found {len(submissions)} submission(s).")
        # Display items using the shared function
        for item in submissions:
            # Pass the selected status so the display function knows the context
            display_submission_item(item, active_status_filter=selected_status)

        # Add a refresh button at the bottom
        st.divider()
        if st.button("🔄 Refresh List"):
            st.rerun()
else:
    st.info("Please select a status from the dropdown above to view submissions.")
