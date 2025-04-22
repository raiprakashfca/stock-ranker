
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe
from datetime import datetime

# Sidebar for Zerodha Token (only if missing in secrets)
if "Access_Token" not in st.secrets:
    st.sidebar.markdown("### 🔐 Zerodha Access Token")
    access_token_input = st.sidebar.text_input("Paste Access Token")
    if st.sidebar.button("Save Token"):
        st.warning("⚠️ This feature works only in local dev mode. On Streamlit Cloud, token must be saved to Google Sheet.")
else:
    st.sidebar.success("✅ Zerodha Token loaded from secrets")

# Load credentials and access the Google Sheet
def get_gsheet_client():
    try:
        credentials_dict = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(credentials_dict)
        client = gspread.authorize(credentials)
        return client
    except Exception as e:
        st.error(f"❌ Failed to authenticate Google Sheets: {e}")
        return None

@st.cache_data(ttl=60)
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

# Main App
st.title("📊 Stock Ranking Dashboard")

df = load_background_analysis()

if df.empty:
    st.warning("No data to display yet.")
else:
    df_display = df.copy()
    df_display["% Change"] = df_display["% Change"].map(lambda x: f"{x:.2f}%" if isinstance(x, (float, int)) else x)
    st.dataframe(df_display.style.applymap(
        lambda v: 'color: green;' if isinstance(v, str) and v.endswith('%') and float(v[:-1]) > 0 else (
                  'color: red;' if isinstance(v, str) and v.endswith('%') and float(v[:-1]) < 0 else '')
    , subset=["% Change"]))
