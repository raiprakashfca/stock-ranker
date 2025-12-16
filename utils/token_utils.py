import os
import json
import base64
import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def _get_sa_raw() -> str:
    # Prefer env (GitHub Actions), else Streamlit secrets (Streamlit Cloud)
    return (os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or st.secrets.get("GOOGLE_SERVICE_ACCOUNT_JSON", "") or "").strip()

def _parse_service_account(raw: str) -> dict:
    """
    Accepts either:
      - plain JSON string
      - base64-encoded JSON string
    Returns dict usable by Credentials.from_service_account_info
    """
    if not raw:
        raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON in secrets/env.")

    # Try plain JSON first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try base64 decode -> JSON
    try:
        decoded = base64.b64decode(raw).decode("utf-8").strip()
        return json.loads(decoded)
    except Exception as e:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON is neither valid JSON nor base64-encoded JSON."
        ) from e

def _client():
    sa_raw = _get_sa_raw()
    info = _parse_service_account(sa_raw)
    creds = Credentials.from_service_account_info(info, scopes=SCOPE)
    return gspread.authorize(creds)

def load_credentials_from_gsheet():
    """
    Reads:
      A1 = api_key
      B1 = api_secret
      C1 = access_token
    from ZerodhaTokenStore sheet KEY (not by name).
    """
    sheet_key = os.getenv("ZERODHA_TOKEN_SHEET_KEY") or st.secrets.get("ZERODHA_TOKEN_SHEET_KEY", "")
    ws_name = os.getenv("ZERODHA_TOKEN_WORKSHEET") or st.secrets.get("ZERODHA_TOKEN_WORKSHEET", "Sheet1")
    if not sheet_key:
        raise RuntimeError("Missing ZERODHA_TOKEN_SHEET_KEY in secrets/env.")

    gc = _client()
    ws = gc.open_by_key(sheet_key).worksheet(ws_name)

    api_key = (ws.acell("A1").value or "").strip()
    api_secret = (ws.acell("B1").value or "").strip()
    access_token = (ws.acell("C1").value or "").strip()

    return api_key, api_secret, access_token

def save_token_to_gsheet(token: str):
    sheet_key = os.getenv("ZERODHA_TOKEN_SHEET_KEY") or st.secrets.get("ZERODHA_TOKEN_SHEET_KEY", "")
    ws_name = os.getenv("ZERODHA_TOKEN_WORKSHEET") or st.secrets.get("ZERODHA_TOKEN_WORKSHEET", "Sheet1")
    if not sheet_key:
        raise RuntimeError("Missing ZERODHA_TOKEN_SHEET_KEY in secrets/env.")

    gc = _client()
    ws = gc.open_by_key(sheet_key).worksheet(ws_name)
    ws.update_acell("C1", token)
