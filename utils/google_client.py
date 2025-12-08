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
    1) GOOGLE_SERVICE_ACCOUNT_JSON env  (JSON string)
    2) GSPREAD_CREDENTIALS_JSON env     (JSON string)
    3) st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"]  (JSON string)
    4) st.secrets["gcp_service_account"]          (TOML table in secrets.toml)
    5) st.secrets["gspread_service_account"]      (TOML table, older pattern)
    """
    # ---- 1 & 2: environment variables ----
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw:
        return json.loads(raw)

    raw = os.environ.get("GSPREAD_CREDENTIALS_JSON")
    if raw:
        return json.loads(raw)

    # ---- 3–5: Streamlit secrets (if running inside Streamlit) ----
    if st is not None:
        # JSON string stored directly
        if "GOOGLE_SERVICE_ACCOUNT_JSON" in st.secrets:
            return json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])

        # Your current pattern: [gcp_service_account] table in secrets.toml
        if "gcp_service_account" in st.secrets:
            # st.secrets["gcp_service_account"] is already a dict-like object
            return dict(st.secrets["gcp_service_account"])

        # Older pattern some apps use
        if "gspread_service_account" in st.secrets:
            return dict(st.secrets["gspread_service_account"])

    raise RuntimeError(
        "Service-account JSON not found. "
        "Set GOOGLE_SERVICE_ACCOUNT_JSON env or add [gcp_service_account] "
        "or GOOGLE_SERVICE_ACCOUNT_JSON to Streamlit secrets."
    )


def get_gspread_client() -> gspread.Client:
    sa_info = _load_service_account_info()
    creds = Credentials.from_service_account_info(sa_info, scopes=SCOPE)
    return gspread.authorize(creds)
