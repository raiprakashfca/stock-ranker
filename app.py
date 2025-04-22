import os
import json
import pandas as pd
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO
from datetime import datetime
from utils.zerodha import get_kite, get_stock_data
from utils.sheet_logger import log_to_google_sheets

st.set_page_config(page_title="📊 Multi-Timeframe Stock Ranking Dashboard", layout="wide")

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

# Sidebar to manage token
st.sidebar.header("🔐 Zerodha API Token Manager")
st.sidebar.info("📅 Timestamp updates on every token refresh.")
if "api_key" not in st.session_state or "access_token" not in st.session_state:
    st.session_state.api_key = ""
    st.session_state.access_token = ""

# Load credentials from secrets
creds_dict = st.secrets["gspread_service_account"]
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

token_sheet = client.open("ZerodhaTokenStore").sheet1
tokens = token_sheet.get_all_values()[0]
api_key, api_secret, access_token = tokens[0], tokens[1], tokens[2]
st.session_state.api_key = api_key
st.session_state.access_token = access_token

# Show login link
login_url = f"https://kite.zerodha.com/connect/login?v=3&api_key={api_key}"
st.sidebar.markdown(f"[🔗 Click here to login and generate access token]({login_url})")

# Token input and update
access_code = st.sidebar.text_input("Paste access token here:")
if st.sidebar.button("🔄 Update Token"):
    token_sheet.update("C1", access_code)
    token_sheet.update("D1", str(datetime.now()))
    st.success("✅ Access token updated successfully.")
    st.rerun()

# Read from Google Sheet
sheet = client.open("BackgroundAnalysisStore").sheet1
data = pd.DataFrame(sheet.get_all_records())

# Format columns
data["% Change"] = data["% Change"].apply(lambda x: f"{x:.2f}%" if isinstance(x, (int, float)) else x)
data["LTP"] = data["LTP"].apply(lambda x: round(x, 2) if isinstance(x, (int, float)) else x)

# Rearranged columns
cols = data.columns.tolist()
reordered_cols = ["Symbol", "LTP", "% Change"] + [col for col in cols if col not in ["Symbol", "LTP", "% Change"]]
data = data[reordered_cols]

# Sorting and filtering
sort_col = st.selectbox("Sort by", [col for col in data.columns if "Score" in col or "Reversal" in col])
ascending = st.radio("Order", ["Descending", "Ascending"]) == "Ascending"
top_n = st.slider("Top N Symbols", 1, len(data), 10)

data = data.sort_values(by=sort_col, ascending=ascending).head(top_n)

# Highlight logic
def highlight_row(row):
    bullish = row["15m Trend Direction"] == "Bullish" and row["1d Trend Direction"] == "Bullish"
    bearish = row["15m Trend Direction"] == "Bearish" and row["1d Trend Direction"] == "Bearish"
    high_score = row["15m TMV Score"] >= 0.8 and row["1d TMV Score"] >= 0.8

    if bullish and high_score:
        return ['background-color: #d4edda; color: black'] * len(row)
    elif bearish and high_score:
        return ['background-color: #f8d7da; color: black'] * len(row)
    else:
        return [''] * len(row)

styled = data.style.apply(highlight_row, axis=1)
st.dataframe(styled, use_container_width=True, hide_index=False)

# Download
buffer = BytesIO()
data.to_excel(buffer, index=False)
st.download_button("📥 Download Excel", buffer.getvalue(), file_name="stock_rankings.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
