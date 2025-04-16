# Moderation_App.py
import streamlit as st
import os

# Credentials
VALID_USERNAME = "moderator"
VALID_PASSWORD = os.getenv("APP_PASSWORD")


def check_credentials(username, password):
    """Validates username and password."""
    return username == VALID_USERNAME and password == VALID_PASSWORD


st.set_page_config(layout="wide", page_title="AI Video Moderation", page_icon="🛡️")

# Initialize session state variables if they don't exist
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False


# --- Display Login Form if not logged in ---
if not st.session_state.logged_in:
    st.title("Login Required")
    st.write("Please enter your credentials to access the application.")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

        if submitted:
            if check_credentials(username, password):
                st.session_state.logged_in = True
                st.session_state.username = username  # Store username
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("Invalid username or password.")

if st.session_state.logged_in:
    # Initialize session state variables if they don't exist
    if "confirmed_rejection" not in st.session_state:
        st.session_state.confirmed_rejection = False
    if "reject_sub_id" not in st.session_state:
        st.session_state.reject_sub_id = None

    st.title("🛡️ AI Video Generation - Moderation Console")

    st.markdown(
        """
    Welcome to the Moderation Console. Use the sidebar navigation to:

    -   **Pending Approvals:** Review and approve/reject submitted photos and generated videos.
    -   **Failed Generations:** Specifically view submissions that failed during video generation and retry them.
    -   **View by Status:** Browse all submissions filtered by their current status.
    -   **Search by Code:** Find a specific submission by entering its unique code, can also be used to retry failed submissions.
    """
    )
