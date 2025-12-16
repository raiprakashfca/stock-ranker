# utils/token_panel.py

import streamlit as st
from kiteconnect import KiteConnect
from utils.token_utils import save_token_to_gsheet


def render_token_panel(api_key: str) -> str | None:
    """
    Renders Zerodha login panel and returns a valid access_token.
    IMPORTANT:
    - Uses api_key passed from app.py (single source of truth)
    - Saves token to ZerodhaTokenStore (C1)
    - Returns token ONLY if validated via kite.profile()
    """

    if not api_key:
        st.error("Missing api_key. Cannot initiate Zerodha login.")
        return None

    st.sidebar.info("🔑 Zerodha login required")

    kite = KiteConnect(api_key=api_key)

    login_url = kite.login_url()
    st.sidebar.markdown(
        f"👉 [Click here to login to Zerodha]({login_url})",
        unsafe_allow_html=True,
    )

    with st.sidebar.form("zerodha_login_form"):
        request_token = st.text_input(
            "Paste request_token from Zerodha after login",
            type="password",
        )
        submitted = st.form_submit_button("Generate Access Token")

    if not submitted:
        return None

    if not request_token:
        st.sidebar.error("Request token cannot be empty.")
        return None

    try:
        session = kite.generate_session(
            request_token=request_token,
            api_secret=None,  # api_secret not needed if already stored server-side
        )
        access_token = session.get("access_token")

        if not access_token:
            raise RuntimeError("No access_token returned by Zerodha.")

        kite.set_access_token(access_token)

        # 🔒 HARD VALIDATION (this is critical)
        kite.profile()

        # Save token centrally
        save_token_to_gsheet(access_token)

        st.sidebar.success("✅ Zerodha login successful. Token saved.")
        return access_token

    except Exception as e:
        st.sidebar.error(f"❌ Zerodha login failed: {e}")
        return None
