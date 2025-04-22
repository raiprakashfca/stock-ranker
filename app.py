import os
import json
import time
import pandas as pd
import streamlit as st
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from utils.zerodha import get_kite, get_stock_data, update_ltp_sheet
from utils.indicators import calculate_scores
from utils.sheet_logger import log_to_google_sheets
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="📊 Multi-Timeframe Stock Ranking Dashboard", layout="wide")

st_autorefresh(interval=5 * 60 * 1000, key="auto_refresh")

# Sidebar with token info
with st.sidebar:
    st.title("🔑 Zerodha API Login")
    try:
        login_url = f"https://kite.trade/connect/login?api_key={st.secrets['Zerodha_API_Key']}"
        st.markdown(f"[Click here to login to Zerodha]({login_url})", unsafe_allow_html=True)
        st.info("📅 Timestamp updates on every token refresh.")
    except Exception as e:
        st.warning("⚠️ Could not create login link. Check secrets config.")

    if st.button("🔄 Refresh Now"):
        update_ltp_sheet()
        st.experimental_rerun()

# Load Google Sheet credentials
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["gspread_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Read stock data from BackgroundAnalysisStore
sheet = client.open("BackgroundAnalysisStore").sheet1
data = pd.DataFrame(sheet.get_all_records())

# Ensure LTP and % Change are right after Symbol
cols = list(data.columns)
ltp_index = cols.index("Symbol") + 1
ltp_col = cols.pop(cols.index("LTP"))
change_col = cols.pop(cols.index("% Change"))
cols.insert(ltp_index, "LTP")
cols.insert(ltp_index + 1, "% Change")
data = data[cols]

# Display sorting options
sort_column = st.selectbox("📊 Sort by", [col for col in data.columns if "Score" in col or "Reversal" in col])
sort_order = st.radio("⬆️⬇️ Order", ["Descending", "Ascending"]) == "Ascending"
limit = st.slider("🔢 Top N Symbols", 1, len(data), min(10, len(data)))

# Sorting and limiting
data = data.sort_values(by=sort_column, ascending=sort_order).head(limit)

# Highlight rules
def highlight_rows(row):
    if (
        row["15m Trend Direction"] == "Bullish"
        and row["1d Trend Direction"] == "Bullish"
        and row["15m TMV Score"] >= 0.8
        and row["1d TMV Score"] >= 0.8
    ):
        return ["background-color: #d4edda; color: black"] * len(row)
    elif (
        row["15m Trend Direction"] == "Bearish"
        and row["1d Trend Direction"] == "Bearish"
        and row["15m TMV Score"] >= 0.8
        and row["1d TMV Score"] >= 0.8
    ):
        return ["background-color: #f8d7da; color: black"] * len(row)
    else:
        return [""] * len(row)

styled = data.style.apply(highlight_rows, axis=1)
st.dataframe(styled, use_container_width=True)
