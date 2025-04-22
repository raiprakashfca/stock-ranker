import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account
from datetime import datetime
from gspread_dataframe import get_as_dataframe

st.set_page_config(page_title="📊 Stock Ranker", layout="wide")

@st.cache_data
def load_background_analysis():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(creds_dict)
        gc = gspread.authorize(creds)

        st.write("✅ Connected to Google Sheets")

        # Debug print sheet names
        sh = gc.open("BackgroundAnalysisStore")
        st.write("📄 Sheet Title:", sh.title)

        # List all worksheets for sanity check
        all_tabs = [ws.title for ws in sh.worksheets()]
        st.write("📑 Available Tabs:", all_tabs)

        ws = sh.worksheet("LiveScores")  # Ensure this matches exactly
        df = pd.DataFrame(ws.get_all_records())
        return df

    except Exception as e:
        st.error(f"❌ Failed to load data from Google Sheet: {e}")
        return pd.DataFrame()

df = load_background_analysis()

if not df.empty:
    st.dataframe(df)
else:
    st.warning("No data found in the sheet.")
