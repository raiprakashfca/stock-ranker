import os
import json
import pandas as pd
import streamlit as st
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="📊 Multi-Timeframe Stock Ranking Dashboard", layout="wide")

# Auto-refresh every 5 minutes
st_autorefresh(interval=5 * 60 * 1000, key="refresh")

# Sidebar
st.sidebar.header("🔐 Zerodha API Token")
st.sidebar.info("📅 Timestamp updates on every token refresh.")

# Google Sheets Auth
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["gspread_service_account"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Load stock data from BackgroundAnalysisStore sheet
try:
    sheet = client.open("BackgroundAnalysisStore").sheet1
    records = sheet.get_all_records()
    if not records:
        st.warning("⚠️ No data found in BackgroundAnalysisStore. Please try again later.")
        st.stop()
    df = pd.DataFrame(records)
except Exception as e:
    st.error(f"❌ Failed to read BackgroundAnalysisStore: {e}")
    st.stop()

# Move LTP and % Change columns next to Symbol
if "LTP" in df.columns and "% Change" in df.columns:
    cols = df.columns.tolist()
    ltp_index = cols.index("LTP")
    pct_index = cols.index("% Change")
    reordered_cols = (
        ["Symbol", "LTP", "% Change"]
        + [col for col in cols if col not in ["Symbol", "LTP", "% Change"]]
    )
    df = df[reordered_cols]

st.title("📊 Multi-Timeframe Stock Ranking Dashboard")

# Sorting & filtering
sort_column = st.selectbox("📌 Sort by", [col for col in df.columns if "Score" in col or "Reversal" in col])
sort_asc = st.radio("🔼 Order", ["Descending", "Ascending"]) == "Ascending"
limit = st.slider("🔢 Top N Symbols", 1, len(df), min(20, len(df)))

df = df.sort_values(by=sort_column, ascending=sort_asc).head(limit)

# Highlighting conditions
highlight_conditions = (
    (df[["15m Trend Direction", "1d Trend Direction"]] == "Bullish").all(axis=1)
    & (df[["15m TMV Score", "1d TMV Score"]] >= 0.8).all(axis=1)
)
highlight_red = (
    (df[["15m Trend Direction", "1d Trend Direction"]] == "Bearish").all(axis=1)
    & (df[["15m TMV Score", "1d TMV Score"]] >= 0.8).all(axis=1)
)

def highlight_row(row):
    if highlight_conditions.loc[row.name]:
        return ["background-color: #c7f3d0; color: black"] * len(row)
    elif highlight_red.loc[row.name]:
        return ["background-color: #f8cfcf; color: black"] * len(row)
    else:
        return [""] * len(row)

# Display styled table
styled_df = df.style.apply(highlight_row, axis=1)
st.dataframe(styled_df, use_container_width=True, hide_index=False)

# Excel export
excel_buffer = BytesIO()
df.to_excel(excel_buffer, index=False)
st.download_button("📥 Download Excel", data=excel_buffer.getvalue(), file_name="stock_rankings.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# API token refresh logic
with st.sidebar.expander("🔁 Update Access Token"):
    api_key = st.text_input("API Key", value="")
    api_secret = st.text_input("API Secret", value="", type="password")
    access_token = st.text_input("Access Token", value="", type="password")

    if st.button("✅ Save Token"):
        try:
            sheet = client.open("ZerodhaTokenStore").sheet1
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet.update("A1:C1", [[api_key, api_secret, access_token]])
            sheet.update("D1", [[timestamp]])
            st.success("🔑 API Token updated successfully!")
        except Exception as e:
            st.error(f"Failed to update token: {e}")
