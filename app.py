import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe
from datetime import datetime

# ========================
# 🔐 Sidebar Token Input (Safe Version)
# ========================
if "Access_Token" not in st.secrets:
    st.sidebar.markdown("### 🔐 Zerodha Access Token")
    access_token_input = st.sidebar.text_input("Paste Access Token", type="password")
    if st.sidebar.button("Save Token"):
        st.warning("⚠️ This feature works only in local mode.\nOn Streamlit Cloud, please update the token in the linked Google Sheet.")
else:
    st.sidebar.success("✅ Zerodha Token loaded from secrets")

# ========================
# 📊 Load Google Sheet Data
# ========================
@st.cache_data(ttl=300)
def load_background_analysis():
    try:
        credentials_dict = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(credentials_dict)
        client = gspread.authorize(credentials)
        sheet = client.open("BackgroundAnalysisStore")
        ws = sheet.worksheet("LiveScores")
        df = pd.DataFrame(ws.get_all_records())
        return df
    except Exception as e:
        st.error(f"❌ Failed to load data from Google Sheet: {e}")
        return pd.DataFrame()

# ========================
# 📌 Main App
# ========================
st.title("📊 Stock TMV Scoreboard")

df = load_background_analysis()

if not df.empty:
    st.dataframe(df, use_container_width=True)
else:
    st.info("No data to display.")
