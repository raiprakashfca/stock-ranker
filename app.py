import streamlit as st
import pandas as pd
from kiteconnect import KiteConnect
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO

from utils.zerodha import get_stock_data
from utils.indicators import calculate_scores
from utils.sheet_logger import log_to_google_sheets

st.set_page_config(page_title="📊 Stock Ranker Dashboard", layout="wide", initial_sidebar_state="expanded")
st.title("📊 Multi-Timeframe Stock Ranking Dashboard")

# Sidebar: Zerodha login and token refresh
st.sidebar.title("🔐 Zerodha Access")
st.sidebar.markdown("Use the link below to login and paste your request token.")

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
try:
    creds_dict = json.loads(st.secrets["gspread_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open("ZerodhaTokenStore").sheet1
    tokens = sheet.get_all_values()[0]
    api_key = tokens[0]
    api_secret = tokens[1]
    access_token = tokens[2]

    st.sidebar.markdown(f"[🔗 Login to Zerodha](https://kite.zerodha.com/connect/login?v=3&api_key={api_key})")
    request_token = st.sidebar.text_input("🔑 Paste Request Token")

    if request_token:
        try:
            kite = KiteConnect(api_key=api_key)
            session = kite.generate_session(request_token, api_secret=api_secret)
            sheet.update_cell(1, 3, session["access_token"])
            st.sidebar.success("✅ Token updated. Please refresh the app.")
            st.stop()
        except Exception as e:
            st.sidebar.error("❌ Token update failed.")
            st.sidebar.exception(e)
except Exception as e:
    st.sidebar.error("❌ Unable to access Google Sheet.")
    st.stop()

# Authenticated Kite connection
kite = KiteConnect(api_key=api_key)
try:
    kite.set_access_token(access_token)
except Exception:
    st.error("⚠️ Access token invalid. Use sidebar to update it.")
    st.stop()

# Configuration
TIMEFRAMES = {
    "15m": {"interval": "15minute", "days": 5},
    "1h": {"interval": "60minute", "days": 15},
    "1d": {"interval": "day", "days": 90},
}
SYMBOLS = ["RELIANCE", "TCS", "INFY", "ICICIBANK", "HDFCBANK", "SBIN", "BHARTIARTL"]

# Data extraction
all_data = []
with st.spinner("🔄 Fetching and scoring data..."):
    for symbol in SYMBOLS:
        row = {"Symbol": symbol}
        for label, config in TIMEFRAMES.items():
            df = get_stock_data(kite, symbol, config["interval"], config["days"])
            if df.empty:
                continue
            try:
                result = calculate_scores(df)
                for key, value in result.items():
                    row[f"{label} | {key}"] = value
            except Exception as e:
                st.warning(f"⚠️ {symbol} {label} failed: {e}")
        all_data.append(row)

if not all_data:
    st.error("❌ No data found.")
    st.stop()

# DataFrame setup
df = pd.DataFrame(all_data)
columns = []
for col in df.columns:
    if col == "Symbol":
        columns.append(("Meta", "Symbol"))
    elif "|" in col:
        tf, metric = map(str.strip, col.split("|"))
        columns.append((tf, metric))
    else:
        columns.append(("Other", col))
df.columns = pd.MultiIndex.from_tuples(columns)
df = df.set_index(("Meta", "Symbol"))

# Display improvements
st.markdown("""
<style>
.stDataFrame td {
  font-size: 12px;
  padding: 4px 6px;
  white-space: nowrap;
}
thead tr th {
  border-bottom: 2px solid #333 !important;
}
th[colspan="3"] {
  border-right: 3px solid #666 !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown("### 🧠 Ranked Score Table")
st.dataframe(df, use_container_width=True, hide_index=False)

# Save to Excel
excel_buffer = BytesIO()
flat_df = df.reset_index()
flat_df.columns = [' '.join(col).strip() if isinstance(col, tuple) else col for col in flat_df.columns]
flat_df.to_excel(excel_buffer, index=False)
st.download_button("📥 Download Excel", data=excel_buffer.getvalue(), file_name="stock_rankings.xlsx")

# Sync to Sheet
try:
    log_to_google_sheets("Combined", flat_df)
    st.success("✅ Logged to Google Sheet")
except Exception as e:
    st.warning(f"⚠️ Sheet log failed: {e}")
