# pages/3_Search_by_Code.py
import streamlit as st

from utils import get_submission_by_code, display_submission_item

st.set_page_config(page_title="Search by Code", page_icon="🔍", layout="centered")

st.header("🔎 Search by Submission Code")
st.caption("Find a specific submission by entering its unique code.")

# --- Input for Submission Code ---
submission_code_input = st.text_input(
    "Enter Submission Code:",
    key="search_code_input",
    help="Enter the exact code of the submission you want to find.",
)

# --- Search Button ---
search_button = st.button("Search", type="primary", use_container_width=True)

st.divider()

# --- Logic for Fetching and Displaying Data ---
if search_button:
    if submission_code_input:
        cleaned_code = submission_code_input.strip()
        if not cleaned_code:
            st.warning("⚠️ Please enter a submission code.")
        else:
            st.subheader(f"Search Results for Code: `{cleaned_code}`")
            with st.spinner(f"⏳ Searching for submission '{cleaned_code}'..."):
                # Assume get_submission_by_code returns the item or None
                submission = get_submission_by_code(cleaned_code)

            if submission:
                st.success("✅ Submission found!")
                st.session_state.search_result = submission
            else:
                st.session_state.search_result = None
                st.error(f"❌ No submission found with the code '{cleaned_code}'. Please check the code and try again.")
    else:
        st.warning("⚠️ Please enter a submission code before searching.")

if st.session_state.get("search_result"):
    display_submission_item(st.session_state.search_result, include_retry=True)
