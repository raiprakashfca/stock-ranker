# 📊 Multi-Timeframe Stock Ranking Dashboard (final integrated version)
import streamlit as st
import pandas as pd
import json
import base64
import gspread
import os
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO

st.set_page_config(page_title="📊 Stock Ranker", layout="wide")

# Sidebar with token management
with st.sidebar:
    st.header("🔐 API Access")
    st.markdown("Visit [Kite Developer](https://kite.trade/apps) to get your API keys.")
    st.markdown("Timestamp gets auto-updated when token is refreshed.")
    if st.button("🔄 Manual Refresh Now"):
        st.experimental_rerun()

# Load Google Sheet credentials from Streamlit secrets
creds_dict = json.loads(st.secrets["gspread_service_account"])
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Load data from BackgroundAnalysisStore
sheet = client.open("BackgroundAnalysisStore").sheet1
data = sheet.get_values()
headers = data[0]
values = data[1:]

df = pd.DataFrame(values, columns=headers)

# Convert numeric columns
numeric_cols = ["LTP", "% Change", "15m TMV Score", "15m Reversal Probability", "1d TMV Score", "1d Reversal Probability"]
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors='coerce')

# Sort and filter
with st.sidebar:
    sort_by = st.selectbox("📊 Sort By", ["15m TMV Score", "1d TMV Score", "% Change"])
    ascending = st.checkbox("⬆️ Sort Ascending", value=False)
    top_n = st.slider("🔢 Show Top N Rows", 1, len(df), 15)

df = df.sort_values(by=sort_by, ascending=ascending).head(top_n)

# Highlight logic
def highlight_row(row):
    bullish = row["15m Trend Direction"] == "Bullish" and row["1d Trend Direction"] == "Bullish"
    bearish = row["15m Trend Direction"] == "Bearish" and row["1d Trend Direction"] == "Bearish"
    high_score = row["15m TMV Score"] >= 0.8 and row["1d TMV Score"] >= 0.8
    if bullish and high_score:
        return ["background-color: #d4edda; color: black"] * len(row)
    elif bearish and high_score:
        return ["background-color: #f8d7da; color: black"] * len(row)
    return [""] * len(row)

styled_df = df.style.apply(highlight_row, axis=1)

# Display
st.title("📈 Stock Ranking Dashboard")
st.dataframe(styled_df, use_container_width=True, hide_index=True)

# Excel Export
excel_buffer = BytesIO()
df.to_excel(excel_buffer, index=False)
st.download_button("📥 Download Excel", data=excel_buffer.getvalue(), file_name="stock_rankings.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
