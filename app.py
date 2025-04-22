
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os

st.set_page_config(page_title="📊 Stock Ranker Dashboard", layout="wide")

# === Load Google Sheet Credentials ===
from google.oauth2.service_account import Credentials

def get_gsheet_client():
    try:
        gcp_credentials = st.secrets["gcp_service_account"]
        scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        credentials = Credentials.from_service_account_info(gcp_credentials, scopes=scopes)
        client = gspread.authorize(credentials)
        return client
    except Exception as e:
        st.error(f"❌ Failed to load credentials: {e}")
        return None

@st.cache_data(ttl=300)
def load_background_analysis():
    try:
        client = get_gsheet_client()
        if client is None:
            return pd.DataFrame()
        sheet = client.open("BackgroundAnalysisStore")
        ws = sheet.worksheet("LiveScores")
        df = pd.DataFrame(ws.get_all_records())
        return df
    except Exception as e:
        st.error(f"❌ Failed to load data from Google Sheet: {e}")
        return pd.DataFrame()

# === UI Sidebar for Access Token Management ===
st.sidebar.header("🔐 Zerodha Access Token")
st.sidebar.markdown(
    "[🔗 Zerodha Login](https://kite.zerodha.com/connect/login?v=3&api_key=" + st.secrets["Zerodha_API_Key"] + ")"
)
st.sidebar.markdown("1. Click the link above to login via Zerodha.\n"
                    "2. After successful login, copy the **Request Token** from the URL.\n"
                    "3. Paste it below and click Submit.")
request_token = st.sidebar.text_input("Paste your Request Token here")
submit_token = st.sidebar.button("Submit Token")

if submit_token and request_token:
    st.sidebar.success("✅ Request Token submitted successfully!")
    st.sidebar.code(request_token)

# === Main App Content ===
st.title("📊 Stock Ranking Dashboard")
df = load_background_analysis()
if not df.empty:
    st.dataframe(df, use_container_width=True)
else:
    st.warning("No data to display.")
