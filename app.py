import json
import os
import pandas as pd
import streamlit as st
import gspread
from io import BytesIO
from kiteconnect import KiteConnect
from oauth2client.service_account import ServiceAccountCredentials
from utils.sheet_logger import log_to_google_sheets

st.set_page_config(page_title="📊 Multi-Timeframe Stock Ranking Dashboard", layout="wide")

# UI Styling
st.markdown("""
<style>
th, td { border-right: 1px solid #ddd; }
.score-badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 8px;
    font-weight: bold;
    min-width: 80px;
    text-align: center;
}
.high { background-color: #28a745; color: white; }
.medium { background-color: #ffc107; color: black; }
.low { background-color: #dc3545; color: white; }
.direction { font-weight: bold; padding: 2px 6px; border-radius: 6px; margin-left: 6px; }
.bullish { background-color: #c6f6d5; color: #22543d; }
.bearish { background-color: #fed7d7; color: #742a2a; }
.neutral { background-color: #fff3cd; color: #856404; }
th:first-child, td:first-child {
  position: sticky;
  left: 0;
  background-color: #2a2a2a;
  z-index: 2;
  color: #fff;
  font-weight: bold;
}
</style>
""", unsafe_allow_html=True)

st.title("📊 Multi-Timeframe Stock Ranking Dashboard")

# Load Google Sheet credentials
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["gspread_credentials_json"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Load Token Info
token_sheet = client.open("ZerodhaTokenStore").sheet1
tokens = token_sheet.get_all_values()[0]
api_key, api_secret, access_token = tokens[0], tokens[1], tokens[2]

# Kite login and fallback
def show_token_sidebar(api_key, api_secret):
    st.sidebar.title("🔐 Refresh Zerodha Token")
    st.sidebar.markdown(f"[Login to Zerodha](https://kite.trade/connect/login?api_key={api_key})", unsafe_allow_html=True)
    access_code = st.sidebar.text_input("Paste access code here:")
    if st.sidebar.button("Generate Token"):
        try:
            kite = KiteConnect(api_key=api_key)
            session = kite.generate_session(access_code, api_secret=api_secret)
            token_sheet.update("C1", session["access_token"])
            st.sidebar.success("✅ Token Updated. Please refresh the app.")
            st.stop()
        except Exception as e:
            st.sidebar.error(f"❌ Token generation failed: {e}")
            st.stop()

try:
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    kite.profile()
except Exception:
    show_token_sidebar(api_key, api_secret)

# Read analysis data
sheet = client.open("BackgroundAnalysisStore").sheet1
df = pd.DataFrame(sheet.get_all_records())

# Sort / Filter Controls
st.markdown("### 🔎 Sort and Filter")
sort_column = st.selectbox("Sort by", ["TMV Score", "% Change"])
sort_asc = st.radio("Order", ["Descending", "Ascending"]) == "Ascending"
limit = st.slider("Top N Symbols", 1, len(df), 10)

df["% Change"] = df["% Change"].str.replace("%", "").astype(float)
df["TMV Score"] = df["TMV Score"].astype(float)

df = df.sort_values(by=sort_column, ascending=sort_asc).head(limit)

# Highlighting
def highlight_row(row):
    if (
        row["15m Trend Direction"] == row["1d Trend Direction"] == "Bullish"
        and row["15m TMV Score"] >= 0.8
        and row["1d TMV Score"] >= 0.8
    ):
        return ["background-color: #d4edda"] * len(row)
    elif (
        row["15m Trend Direction"] == row["1d Trend Direction"] == "Bearish"
        and row["15m TMV Score"] >= 0.8
        and row["1d TMV Score"] >= 0.8
    ):
        return ["background-color: #f8d7da"] * len(row)
    else:
        return [""] * len(row)

styled = df.style.apply(highlight_row, axis=1)

st.markdown("### 📊 Live Stock Ranking (15m + 1d Analysis)")
st.dataframe(styled, use_container_width=True)

# Download
excel_buffer = BytesIO()
df.to_excel(excel_buffer, index=False)
st.download_button("📥 Download Excel", data=excel_buffer.getvalue(), file_name="stock_rankings.xlsx")

try:
    log_to_google_sheets(sheet_name="Combined", df=df)
    st.success("✅ Logged to Google Sheet.")
except Exception as e:
    st.warning(f"⚠️ Could not update Google Sheet: {e}")
