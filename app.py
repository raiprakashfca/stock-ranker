
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# === Page Config ===
st.set_page_config(page_title="📊 Stock Ranker Dashboard", layout="wide")

# === Google Sheets Config ===
SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

GCP_CREDENTIALS = st.secrets["gcp_service_account"]
CREDS = Credentials.from_service_account_info(GCP_CREDENTIALS, scopes=SCOPE)
client = gspread.authorize(CREDS)

@st.cache_data(ttl=60)
def load_background_analysis():
    try:
        sheet = client.open("BackgroundAnalysisStore")
        ws = sheet.worksheet("LiveScores")
        df = pd.DataFrame(ws.get_all_records())
        return df
    except Exception as e:
        st.error(f"❌ Failed to load data from Google Sheet: {e}")
        return pd.DataFrame()

df = load_background_analysis()

# === App Layout ===
st.title("📊 Stock Ranker Dashboard")
st.markdown("Live scores from background analysis")

if not df.empty:
    # Reorder columns if they exist
    columns_order = [
        "Symbol", "LTP", "% Change",
        "15m TMV Score", "15m Trend Direction", "15m Reversal Probability",
        "1d TMV Score", "1d Trend Direction", "1d Reversal Probability"
    ]
    df = df[[col for col in columns_order if col in df.columns]]
    st.dataframe(df, use_container_width=True)
else:
    st.warning("No data found in the sheet. Please check the BackgroundAnalysisStore sheet.")
