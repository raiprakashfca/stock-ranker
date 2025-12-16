import os, json
import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def _client():
    sa = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or st.secrets.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not sa:
        raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON in secrets/env.")
    creds = Credentials.from_service_account_info(json.loads(sa), scopes=SCOPE)
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
    api_key = ws.acell("A1").value
    api_secret = ws.acell("B1").value
    access_token = ws.acell("C1").value
    return api_key, api_secret, access_token

def save_token_to_gsheet(token: str):
    sheet_key = os.getenv("ZERODHA_TOKEN_SHEET_KEY") or st.secrets.get("ZERODHA_TOKEN_SHEET_KEY", "")
    ws_name = os.getenv("ZERODHA_TOKEN_WORKSHEET") or st.secrets.get("ZERODHA_TOKEN_WORKSHEET", "Sheet1")
    if not sheet_key:
        raise RuntimeError("Missing ZERODHA_TOKEN_SHEET_KEY in secrets/env.")
    gc = _client()
    ws = gc.open_by_key(sheet_key).worksheet(ws_name)
    ws.update_acell("C1", token)
