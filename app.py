
import json
import os
import time
import pandas as pd
import streamlit as st
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO
from utils.zerodha import get_kite, get_stock_data, update_ltp_sheet
from utils.indicators import calculate_scores
from utils.sheet_logger import log_to_google_sheets

st.set_page_config(page_title="📊 Multi-Timeframe Stock Ranking Dashboard", layout="wide")

# Sidebar content
st.sidebar.title("🔑 API & Data Controls")
st.sidebar.info("📅 Timestamp updates on every token refresh.")

if "Zerodha_API_Key" in st.secrets:
    login_url = f"https://kite.trade/connect/login?api_key={st.secrets['Zerodha_API_Key']}"
    st.sidebar.markdown(f"[🔐 Login to Zerodha]({login_url})", unsafe_allow_html=True)
else:
    st.sidebar.warning("⚠️ Zerodha API Key not found in secrets.")

# Add manual refresh button
if st.button("🔁 Refresh Now"):
    update_ltp_sheet()
    st.experimental_rerun()

# Google Sheets credentials
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["gspread_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Read processed data
sheet = client.open("BackgroundAnalysisStore").sheet1
data = pd.DataFrame(sheet.get_all_records())

if data.empty:
    st.warning("⚠️ No data found in BackgroundAnalysisStore.")
    st.stop()

# Reorder columns to ensure LTP and % Change are right after Symbol
cols = data.columns.tolist()
if "LTP" in cols and "% Change" in cols:
    cols.insert(1, cols.pop(cols.index("LTP")))
    cols.insert(2, cols.pop(cols.index("% Change")))
    data = data[cols]

# Sort and filter
sort_column = st.selectbox("Sort by", [col for col in data.columns if "Score" in col or "Reversal" in col])
sort_asc = st.radio("Order", ["Descending", "Ascending"]) == "Ascending"
limit = st.slider("Top N Symbols", 1, len(data), 10)
data = data.sort_values(by=sort_column, ascending=sort_asc).head(limit)

# Highlight logic
highlight_green = (
    (data[["15m Trend Direction", "1d Trend Direction"]] == "Bullish").all(axis=1) &
    (data[["15m TMV Score", "1d TMV Score"]] >= 0.8).all(axis=1)
)
highlight_red = (
    (data[["15m Trend Direction", "1d Trend Direction"]] == "Bearish").all(axis=1) &
    (data[["15m TMV Score", "1d TMV Score"]] >= 0.8).all(axis=1)
)

def highlight_row(row):
    if highlight_green.loc[row.name]:
        return ["background-color: #d4edda; color: black;"] * len(row)
    elif highlight_red.loc[row.name]:
        return ["background-color: #f8d7da; color: black;"] * len(row)
    else:
        return [""] * len(row)

styled_df = data.style.apply(highlight_row, axis=1)
st.dataframe(styled_df, use_container_width=True, hide_index=False)

# Export
excel_buffer = BytesIO()
data.to_excel(excel_buffer, index=False)
st.download_button("📥 Download Excel", data=excel_buffer.getvalue(), file_name="stock_rankings.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# Auto refresh every 5 mins
st_autorefresh = st.experimental_rerun
if int(time.time()) % 300 == 0:
    st_autorefresh()
