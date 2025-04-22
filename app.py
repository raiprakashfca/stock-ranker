import os
import json
import pandas as pd
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from io import BytesIO
from streamlit_autorefresh import st_autorefresh
# ==================== DEBUG BLOCK START ====================
import json

st.subheader("🔍 Debug Secrets Check")
st.write("Secrets keys detected:", list(st.secrets.keys()))

try:
    service_account_info = dict(st.secrets["gcp_service_account"])
    st.success("✅ gcp_service_account block found!")
    st.json(service_account_info)
except Exception as e:
    st.error(f"❌ Failed to read gcp_service_account: {e}")
# ==================== DEBUG BLOCK END ======================
# App layout
st.set_page_config(page_title="📊 Multi-Timeframe Stock Ranking Dashboard", layout="wide")

st.title("📊 Multi-Timeframe Stock Ranking Dashboard")

# Auto-refresh every 5 minutes
st_autorefresh(interval=5 * 60 * 1000, key="data_refresh")

# Secrets fallback
try:
    creds_dict = json.loads(st.secrets["gspread_service_account"])
except Exception:
    st.error("❌ Missing or invalid Google Sheets credentials. Please check your Streamlit secrets.")
    st.stop()

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Load LiveLTPStore sheet with expected headers
try:
    sheet = client.open("LiveLTPStore").sheet1
    records = sheet.get_all_records(expected_headers=["Symbol", "LTP", "% Change"])
    ltp_df = pd.DataFrame(records)
except Exception as e:
    st.error(f"❌ Could not load sheet data: {e}")
    st.stop()

# Display control options
with st.sidebar:
    st.header("🔧 Controls")
    st.markdown("✅ LTP auto-refreshes every 5 minutes.")
    refresh_button = st.button("🔄 Manual Refresh")
    st.markdown("---")

if refresh_button:
    st.experimental_rerun()

# Display data
st.subheader("📈 Live LTPs and % Changes")
if not ltp_df.empty:
    def highlight(row):
        style = []
        if row["% Change"] > 1.5:
            style = ["background-color: #d4edda; color: black"] * len(row)
        elif row["% Change"] < -1.5:
            style = ["background-color: #f8d7da; color: black"] * len(row)
        else:
            style = [""] * len(row)
        return style

    ltp_df = ltp_df[["Symbol", "LTP", "% Change"]]  # Ensure correct order
    st.dataframe(ltp_df.style.apply(highlight, axis=1), use_container_width=True)
else:
    st.warning("⚠️ No LTP data found in the sheet.")
