# pages/3_Failed_Generations.py
import streamlit as st
from utils import get_submissions_by_status, display_submission_item, STATUS_GENERATION_FAILED, retry_generation
import time

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
        display_submission_item(item, active_status_filter=status_to_fetch)

    # Add a refresh button at the bottom
    st.divider()
    if st.button("🔄 Refresh List"):
        st.rerun()
