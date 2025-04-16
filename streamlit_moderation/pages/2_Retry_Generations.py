# pages/3_Failed_Generations.py
import streamlit as st
from utils import get_submissions_by_status, display_submission_item, STATUS_GENERATION_FAILED
import time

st.set_page_config(page_title="Failed Generations", page_icon="🛡️", layout="centered")

# Check if user is logged in
if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.switch_page("Moderation_App.py")

st.header("🛠️ Failed Video Generations")
st.caption("View submissions where video generation failed and retry them.")

# Fetch failed items
status_to_fetch = STATUS_GENERATION_FAILED
st.subheader(f"Items with Status: `{status_to_fetch}`")

with st.spinner(f"⏳ Fetching submissions with status '{status_to_fetch}'..."):
    failed_items = get_submissions_by_status(status_to_fetch)

if not failed_items:
    st.info(f"✅ No submissions currently have the status '{status_to_fetch}'.")
else:
    st.caption(f"Found {len(failed_items)} failed submission(s).")
    # Display items using the shared function - it will show the 'Retry' button
    for item in failed_items:
        display_submission_item(item, include_retry=True)

    if st.sidebar.button(":material/refresh: Refresh List", use_container_width=True):
        st.rerun()
