
import streamlit as st
import pandas as pd
from token_utils import load_credentials_from_gsheet

st.set_page_config(page_title="📊 TMV Stock Ranking", layout="wide")

# Load API Key from secrets
api_key = st.secrets["Zerodha_API_Key"]

# Sidebar for Zerodha login
st.sidebar.markdown("## 🔐 Zerodha Access Token Setup")
login_url = f"https://kite.zerodha.com/connect/login?v=3&api_key={api_key}"
st.sidebar.markdown(f"[🔗 Login to Zerodha]({login_url})", unsafe_allow_html=True)
access_token = st.sidebar.text_input("Paste Access Token Here")

# Main content
st.title("📈 Multi-Timeframe TMV Stock Ranking Dashboard")

# Load Background Analysis data
sheet_url = "https://docs.google.com/spreadsheets/d/your-sheet-id/edit#gid=0"
csv_export_url = sheet_url.replace("/edit#gid=", "/export?format=csv&gid=")
try:
    df = pd.read_csv(csv_export_url)
    df = df[["Symbol", "LTP", "% Change", "15m TMV Score", "15m Trend Direction", "15m Reversal Probability", 
             "1d TMV Score", "1d Trend Direction", "1d Reversal Probability"]]
    st.dataframe(df, use_container_width=True)
except Exception as e:
    st.error(f"Failed to load data from Google Sheet: {e}")
