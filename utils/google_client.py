# utils/google_client.py
import os, json
from typing import Dict, Any

import gspread
from google.oauth2.service_account import Credentials

try:
    import streamlit as st  # type: ignore
except Exception:
    st = None

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def _load_service_account_info() -> Dict[str, Any]:
    # 1) env var (works for Streamlit + jobs)
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw:
        return json.loads(raw)

    # 2) Streamlit secrets direct JSON string
    if st is not None:
        if "GOOGLE_SERVICE_ACCOUNT_JSON" in st.secrets:
            return json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])

        # 3) common alternate key name
        if "gcp_service_account" in st.secrets:
            return dict(st.secrets["gcp_service_account"])

        if "gspread_service_account" in st.secrets:
            return dict(st.secrets["gspread_service_account"])

    raise RuntimeError(
        "Google service account not found. Add GOOGLE_SERVICE_ACCOUNT_JSON to Streamlit secrets "
        "or environment variables."
    )

def get_gspread_client() -> gspread.Client:
    info = _load_service_account_info()
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)
