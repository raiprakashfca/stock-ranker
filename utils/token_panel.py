# utils/token_panel.py
# Zerodha login + token management panel for Streamlit.

import datetime as dt
from urllib.parse import urlparse, parse_qs
from typing import Optional

import streamlit as st
from kiteconnect import KiteConnect

from .token_store import write_access_token, read_token_row


IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def _kite(api_key: str) -> KiteConnect:
    return KiteConnect(api_key=api_key)


def zerodha_login_url(api_key: str) -> str:
    kite = _kite(api_key)
    return kite.login_url()


def exchange_request_token(api_key: str, api_secret: str, request_token: str) -> str:
    kite = KiteConnect(api_key=api_key)
    session_data = kite.generate_session(
        request_token=request_token,
        api_secret=api_secret,
    )
    return session_data["access_token"]


def verify_access_token(api_key: str, access_token: str) -> bool:
    try:
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)
        kite.profile()
        return True
    except Exception:
        return False


def extract_request_token_from_text(pasted: str) -> Optional[str]:
    pasted = (pasted or "").strip()
    if not pasted:
        return None
    try:
        qs = parse_qs(urlparse(pasted).query)
        rt = qs.get("request_token", [None])[0]
        if rt:
            return rt
    except Exception:
        pass
    if 20 <= len(pasted) <= 64 and pasted.isalnum():
        return pasted
    return None


def render_token_panel():
    tr = read_token_row()
    api_key, api_secret = tr.api_key, tr.api_secret

    st.subheader("Zerodha Login (Token Manager)")

    cols = st.columns([1, 2])
    with cols[0]:
        if st.button("🔑 Open Zerodha Login", use_container_width=True):
            st.markdown(
                f"[Click here if it didn't open automatically]({zerodha_login_url(api_key)})"
            )
    with cols[1]:
        st.caption(
            "Complete Zerodha login & 2FA, then copy the redirect URL (contains `request_token`)."
        )

    pasted = st.text_input(
        "Paste redirect URL or token:",
        value="",
        help="We’ll auto-detect whether it's a request_token or an access_token.",
    )
    do_save = st.button("Save Token to Sheet")

    if not do_save:
        return None

    if not pasted.strip():
        st.error("Please paste the redirect URL or token.")
        return None

    # Try as request_token
    req_tok = extract_request_token_from_text(pasted)
    if req_tok:
        try:
            access_token = exchange_request_token(api_key, api_secret, req_tok)
            if not verify_access_token(api_key, access_token):
                st.error("Exchanged token failed verification.")
                return None
            write_access_token(access_token)
            st.success("Access token generated, verified, and saved ✅")
            st.session_state["access_token"] = access_token
            return access_token
        except Exception as e:
            st.warning(
                f"Request-token exchange failed ({e}). "
                "Trying pasted text as access_token directly..."
            )

    candidate = pasted.strip()
    if verify_access_token(api_key, candidate):
        write_access_token(candidate)
        st.success("Access token verified and saved ✅")
        st.session_state["access_token"] = candidate
        return candidate

    st.error("Could not use the pasted text. Please re-login and paste the FULL redirect URL.")
    return None
