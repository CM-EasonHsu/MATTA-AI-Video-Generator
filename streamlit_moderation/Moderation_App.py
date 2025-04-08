# Moderation_App.py
import streamlit as st
from utils import BACKEND_API_URL  # Import necessary things if needed globally

st.set_page_config(
    layout="wide", page_title="AI Video Moderation", page_icon="🛡️"  # Use wide layout for potentially more content
)

# Initialize session state variables if they don't exist
if "confirmed_rejection" not in st.session_state:
    st.session_state.confirmed_rejection = False
if "reject_sub_id" not in st.session_state:
    st.session_state.reject_sub_id = None
# Add any other session state variables you might need globally

st.title("🛡️ AI Video Generation - Moderation Console")

st.markdown(
    """
Welcome to the Moderation Console. Use the sidebar navigation to:

-   **Pending Approvals:** Review and approve/reject submitted photos and generated videos.
-   **View by Status:** Browse all submissions filtered by their current status.
-   **Failed Generations:** Specifically view submissions that failed during video generation and retry them.
"""
)

st.sidebar.success("Select a moderation task above.")

# You can add more dashboard elements or summaries here if needed.
st.info(f"Connected to Backend API: `{BACKEND_API_URL}`")
