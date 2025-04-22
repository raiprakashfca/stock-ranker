import os
import json
import pandas as pd
import streamlit as st
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="📊 Multi-Timeframe Stock Ranking", layout="wide")

# 🔁 Auto-refresh every 5 minutes
st_autorefresh(interval=5 * 60 * 1000, key="refresh")

# 🔐 Load credentials
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["gspread_service_account"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# 🧾 Sidebar with login and timestamp
st.sidebar.title("🔑 Zerodha Access")
try:
    token_sheet = client.open("ZerodhaTokenStore").sheet1
    tokens = token_sheet.get_all_values()[0]
    api_key, api_secret, access_token, timestamp = tokens[0], tokens[1], tokens[2], tokens[3]
except Exception:
    api_key, access_token, timestamp = "Unavailable", "Unavailable", "N/A"

login_url = f"https://kite.trade/connect/login?api_key={api_key}"
st.sidebar.markdown(f"🔗 [Login to Zerodha]({login_url})")
st.sidebar.write(f"🪪 Access Token: `{access_token[:6]}...`")
st.sidebar.write(f"📅 Last Updated: `{timestamp}`")
st.sidebar.info("📅 Timestamp updates on every token refresh.")

# 🔁 Manual refresh
if st.sidebar.button("🔄 Manual Refresh Now"):
    st.experimental_rerun()

st.title("📊 Multi-Timeframe Stock Ranking Dashboard")

# 🗂 Load background analysis sheet
try:
    sheet = client.open("BackgroundAnalysisStore").sheet1
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
except Exception as e:
    st.error(f"❌ Failed to load Google Sheet: {e}")
    st.stop()

if df.empty:
    st.warning("⚠️ No data available in BackgroundAnalysisStore.")
    st.stop()

# 🧹 Data cleanup
df["LTP"] = pd.to_numeric(df["LTP"], errors="coerce")
df["% Change"] = df["% Change"].str.replace('%', '', regex=False).astype(float)
for col in df.columns:
    if "Score" in col or "Reversal" in col:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# 🧮 Sorting options
sort_column = st.selectbox("📌 Sort By", [col for col in df.columns if "Score" in col or "Reversal" in col])
sort_asc = st.radio("↕️ Sort Order", ["Descending", "Ascending"]) == "Ascending"
limit = st.slider("🎯 Show Top N", min_value=5, max_value=len(df), value=10)

# 🗃 Sort and filter
df = df.sort_values(by=sort_column, ascending=sort_asc).head(limit)

# 🟩 Highlight logic
highlight_green = (
    (df[["15m Trend Direction", "1d Trend Direction"]] == "Bullish").all(axis=1) &
    (df[["15m TMV Score", "1d TMV Score"]] >= 0.8).all(axis=1)
)

highlight_red = (
    (df[["15m Trend Direction", "1d Trend Direction"]] == "Bearish").all(axis=1) &
    (df[["15m TMV Score", "1d TMV Score"]] >= 0.8).all(axis=1)
)

def highlight_row(row):
    if highlight_green.loc[row.name]:
        return ['background-color: #c6f6d5; color: black'] * len(row)
    elif highlight_red.loc[row.name]:
        return ['background-color: #f8d7da; color: black'] * len(row)
    else:
        return [''] * len(row)

# 📊 Show table
styled_df = df.style.apply(highlight_row, axis=1)
st.dataframe(styled_df, use_container_width=True)

# 💾 Download
buffer = BytesIO()
df.to_excel(buffer, index=False)
st.download_button("📥 Download Excel", data=buffer.getvalue(), file_name="stock_rankings.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
