# utils/token_panel.py
# Streamlit login panel that:
#  - Opens Zerodha login (one click)
#  - Accepts pasted redirect URL OR request_token OR access_token
#  - Exchanges request_token -> access_token
#  - Verifies token against Kite -> saves to Google Sheet with timestamps

import os, json, datetime as dt
from urllib.parse import urlparse, parse_qs
from typing import Optional, Tuple

import streamlit as st

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

# ---------- Google Sheets helpers ----------
def _gspread():
    import gspread
    from google.oauth2.service_account import Credentials
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not sa_json:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON env not set")
    creds = Credentials.from_service_account_info(
        json.loads(sa_json),
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds)

def _open_token_sheet():
    key = os.getenv("ZERODHA_TOKEN_SHEET_KEY", "")
    if not key:
        raise RuntimeError("ZERODHA_TOKEN_SHEET_KEY env not set")
    return _gspread().open_by_key(key).sheet1  # A1..E1 schema

def read_api_key_secret() -> Tuple[str, str]:
    ws = _open_token_sheet()
    row = ws.row_values(1) + ["", "", "", "", ""]
    api_key, api_secret = (row[0] or "").strip(), (row[1] or "").strip()
    if not api_key or not api_secret:
        raise RuntimeError("ZerodhaTokenStore missing API Key/Secret in A1/B1")
    return api_key, api_secret

def write_access_token(access_token: str, ttl_hours: int = 24):
    ws = _open_token_sheet()
    now = dt.datetime.now(IST)
    # expire slightly early for safety
    expires_at = now + dt.timedelta(hours=ttl_hours - 0.25)
    ws.update("C1", access_token)
    ws.update("D1", expires_at.isoformat())
    ws.update("E1", now.isoformat())

# ---------- Zerodha helpers ----------
def _kite():
    from kiteconnect import KiteConnect
    api_key, _ = read_api_key_secret()
    return KiteConnect(api_key=api_key)

def zerodha_login_url() -> str:
    kite = _kite()
    # If you want to force a specific redirect (not required for paste flow), set in dev console.
    return kite.login_url()

def exchange_request_token(request_token: str) -> str:
    from kiteconnect import KiteConnect
    api_key, api_secret = read_api_key_secret()
    kite = KiteConnect(api_key=api_key)
    session_data = kite.generate_session(request_token=request_token, api_secret=api_secret)
    return session_data["access_token"]

def verify_access_token(access_token: str) -> bool:
    try:
        from kiteconnect import KiteConnect
        api_key, _ = read_api_key_secret()
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)
        kite.margins()  # lightweight sanity call
        return True
    except Exception:
        return False

# ---------- Parsing helpers ----------
def extract_request_token_from_text(pasted: str) -> Optional[str]:
    """
    Accepts:
      - Full redirect URL (contains ?request_token=...)
      - Raw 'request_token' string
      - Or returns None if not found
    """
    pasted = (pasted or "").strip()
    if not pasted:
        return None
    # Try URL parse
    try:
        qs = parse_qs(urlparse(pasted).query)
        rt = qs.get("request_token", [None])[0]
        if rt:
            return rt
    except Exception:
        pass
    # If it's not a URL, it might be the token itself (alphanumeric ~32 chars)
    if 20 <= len(pasted) <= 64 and pasted.isalnum():
        # Could be request_token OR access_token; we treat it as request_token first.
        return pasted
    return None

def looks_like_access_token(pasted: str) -> bool:
    # Access tokens are opaque strings; heuristic: if verify() passes, it's an access token.
    return False  # we don't pre-guess; we verify after trying request_token flow

# ---------- The panel ----------
def render_token_panel():
    st.subheader("Zerodha Login (One-Click + Paste)")

    # 1) Open official Zerodha login
    col1, col2 = st.columns([1,2])
    with col1:
        if st.button("🔑 Open Zerodha Login", use_container_width=True):
            st.markdown(f"[Click here if it didn't open automatically]({zerodha_login_url()})")

    with col2:
        st.caption("Finish login & 2FA, then copy the browser’s redirect URL (it contains `request_token`).")

    # 2) Paste box (URL / request_token / access_token)
    pasted = st.text_input("Paste redirect URL or request_token (or an existing access_token):", value="", type="default", help="We’ll auto-detect and do the right thing.")
    do_save = st.button("Save Token to Sheet")

    if not do_save:
        st.info("After login, paste and click **Save Token to Sheet**.")
        return None  # no token yet

    if not pasted.strip():
        st.error("Nothing pasted. Please paste the redirect URL or token.")
        return None

    # Try request_token flow first
    req_tok = extract_request_token_from_text(pasted)
    if req_tok:
        try:
            access_token = exchange_request_token(req_tok)
            if not verify_access_token(access_token):
                st.error("Exchanged token failed verification. Please retry login.")
                return None
            write_access_token(access_token)
            st.success("Access token generated, verified, and saved to Google Sheet ✅")
            st.session_state["access_token"] = access_token
            return access_token
        except Exception as e:
            st.warning(f"Request-token exchange failed ({e}). Will attempt to treat your paste as an access_token directly...")

    # If exchange failed or it wasn’t a request_token, try verifying pasted string as an access token directly
    candidate = pasted.strip()
    if verify_access_token(candidate):
        write_access_token(candidate)
        st.success("Access token verified and saved to Google Sheet ✅")
        st.session_state["access_token"] = candidate
        return candidate

    st.error("Could not use the pasted text as request_token or access_token. Please re-login and paste the FULL redirect URL.")
    return None
