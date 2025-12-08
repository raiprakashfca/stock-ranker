# utils/google_client.py

import os
import json
from typing import Any, Dict

import gspread
from google.oauth2.service_account import Credentials

try:
    import streamlit as st  # type: ignore
except ImportError:
    st = None  # jobs / CLI won't have Streamlit


SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _load_service_account_info() -> Dict[str, Any]:
    """
    Unified loader for service-account JSON.

    Priority:
    1) GOOGLE_SERVICE_ACCOUNT_JSON env
    2) GSPREAD_CREDENTIALS_JSON env
    3) st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"]
    4) st.secrets["gspread_service_account"]
    """
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw:
        return json.loads(raw)

    raw = os.environ.get("GSPREAD_CREDENTIALS_JSON")
    if raw:
        return json.loads(raw)

    if st is not None:
        if "GOOGLE_SERVICE_ACCOUNT_JSON" in st.secrets:
            return json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
        if "gspread_service_account" in st.secrets:
            # already a dict-like secret
            return dict(st.secrets["gspread_service_account"])

    raise RuntimeError(
        "Service-account JSON not found. "
        "Set GOOGLE_SERVICE_ACCOUNT_JSON env or Streamlit secrets."
    )


def get_gspread_client() -> gspread.Client:
    sa_info = _load_service_account_info()
    creds = Credentials.from_service_account_info(sa_info, scopes=SCOPE)
    return gspread.authorize(creds)
