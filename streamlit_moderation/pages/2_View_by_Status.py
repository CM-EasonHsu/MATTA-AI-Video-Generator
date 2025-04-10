# pages/2_View_by_Status.py
import streamlit as st

# Make sure to import the new count function and math
from utils import (
    get_submissions_by_status,
    get_submissions_count_by_status,
    display_submission_item,
    ALL_STATUSES,
)
import math

st.set_page_config(page_title="View by Status", page_icon="🛡️", layout="centered")

st.header("📊 View Submissions by Status")
st.caption("Browse submissions based on their current processing status.")

# --- Constants ---
PAGE_SIZE = 10  # Number of items per page

# --- Session State Initialization ---
# Keep track of the currently selected status to reset page number on change
if "view_by_status_selected" not in st.session_state:
    st.session_state.view_by_status_selected = None
# Keep track of the current page number
if "view_by_status_current_page" not in st.session_state:
    st.session_state.view_by_status_current_page = 1

# Ensure session state for rejection dialog is initialized (if used by display_submission_item)
if "confirmed_rejection" not in st.session_state:
    st.session_state.confirmed_rejection = False
if "reject_sub_id" not in st.session_state:
    st.session_state.reject_sub_id = None


# --- Status Selection ---
selected_status = st.selectbox(
    "Select Status to View:",
    options=ALL_STATUSES,
    index=None,
    placeholder="Choose a status...",
    key="status_selector",  # Assign a key for potential interaction tracking
)

st.divider()

# --- Logic for Fetching and Displaying Data ---
if selected_status:
    # Reset page number if the status selection has changed
    if st.session_state.view_by_status_selected != selected_status:
        st.session_state.view_by_status_current_page = 1
        st.session_state.view_by_status_selected = selected_status

    st.subheader(f"Submissions with Status: `{selected_status}`")

    # --- Fetch Total Count (for pagination calculation) ---
    with st.spinner(f"⏳ Counting submissions with status '{selected_status}'..."):
        total_items = get_submissions_count_by_status(selected_status)

    if total_items == 0:
        st.info(f"✅ No submissions found with the status '{selected_status}'.")
    else:
        # --- Calculate Pagination Details ---
        total_pages = math.ceil(total_items / PAGE_SIZE)
        current_page = st.session_state.view_by_status_current_page

        # Ensure current page is valid (e.g., if items were deleted)
        if current_page > total_pages:
            current_page = total_pages
            st.session_state.view_by_status_current_page = current_page
        if current_page < 1:  # Should not happen with current logic, but good practice
            current_page = 1
            st.session_state.view_by_status_current_page = current_page

        # Calculate skip value for the API call
        skip_items = (current_page - 1) * PAGE_SIZE

        # --- Fetch Submissions for the Current Page ---
        with st.spinner(
            f"⏳ Fetching submissions {skip_items + 1} - {min(skip_items + PAGE_SIZE, total_items)} of {total_items}..."
        ):
            submissions = get_submissions_by_status(selected_status, skip=skip_items, limit=PAGE_SIZE)

        if not submissions and current_page > 1:
            # This can happen if items were deleted on the last page after count was fetched
            st.warning(f"No submissions found on page {current_page}. Trying the previous page.")
            st.session_state.view_by_status_current_page -= 1
            st.rerun()  # Rerun to fetch the previous page
        elif not submissions and current_page == 1:
            st.info(
                f"✅ No submissions found with the status '{selected_status}'."
            )  # Should have been caught by total_items == 0, but as a fallback
        else:
            st.caption(f"Showing {len(submissions)} submission(s) on this page (Total: {total_items}).")
            # Display items using the shared function
            for item in submissions:
                # Pass the selected status so the display function knows the context
                display_submission_item(item)

            # --- Pagination Controls ---
            if total_pages > 1:
                col1, col2, col3 = st.sidebar.columns([1, 2, 1])

                with col1:
                    # Disable 'Previous' button if on the first page
                    if st.button(":material/arrow_back:", disabled=(current_page <= 1), use_container_width=True):
                        st.session_state.view_by_status_current_page -= 1
                        st.rerun()  # Rerun the script to reflect the change

                with col2:
                    st.button(
                        f"Page {current_page} of {total_pages}", use_container_width=True, disabled=True, type="primary"
                    )

                with col3:
                    # Disable 'Next' button if on the last page
                    if st.button(
                        ":material/arrow_forward:", disabled=(current_page >= total_pages), use_container_width=True
                    ):
                        st.session_state.view_by_status_current_page += 1
                        st.rerun()  # Rerun the script to reflect the change

            # --- Refresh Button ---
            if st.sidebar.button(":material/refresh: Refresh List", use_container_width=True):
                st.rerun()

else:
    st.info("Please select a status from the dropdown above to view submissions.")
