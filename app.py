import json
import pandas as pd
import streamlit as st
import gspread
import os
from kiteconnect import KiteConnect
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO
from streamlit_autorefresh import st_autorefresh

# Set page config
st.set_page_config(page_title="📊 Multi-Timeframe Stock Ranking Dashboard", layout="wide")

# --- SIDEBAR: Zerodha Login ---
with st.sidebar:
    st.header("🔐 Zerodha API Token Setup")
    sheet_scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["gspread_service_account"])
    client = gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, sheet_scope))

    token_sheet = client.open("ZerodhaTokenStore").sheet1
    tokens = token_sheet.get_all_values()[0]

    api_key = tokens[0]
    api_secret = tokens[1]
    access_token = tokens[2] if len(tokens) > 2 else ""

    st.markdown(f"🔗 **[Click here to login](https://kite.trade/connect/login?api_key={api_key})**")
    code_input = st.text_input("Paste Access Code")
    if st.button("🔁 Generate Token"):
        kite = KiteConnect(api_key=api_key)
        try:
            data = kite.generate_session(code_input, api_secret=api_secret)
            new_access_token = data["access_token"]
            token_sheet.update("A1", [[api_key, api_secret, new_access_token]])
            st.success("✅ Access Token Updated Successfully!")
        except Exception as e:
            st.error(f"❌ Failed to generate token: {e}")

# --- Refresh every 5 minutes ---
st_autorefresh(interval=5 * 60 * 1000, key="auto_refresh")

# --- Load Live Data Sheet ---
ltp_sheet = client.open("BackgroundAnalysisStore").sheet1
try:
    df = pd.DataFrame(ltp_sheet.get_all_records())
    if df.empty:
        st.warning("⚠️ No data found in BackgroundAnalysisStore. Please check if the cron job ran successfully.")
        st.stop()
except Exception as e:
    st.error(f"❌ Failed to load Google Sheet: {e}")
    st.stop()

# --- Display Main Table ---
st.title("📊 Multi-Timeframe Stock Ranking Dashboard")

sort_col = st.selectbox("Sort by", ["15m TMV Score", "1d TMV Score", "% Change"])
sort_order = st.radio("Order", ["Descending", "Ascending"]) == "Ascending"

# Format columns
df["% Change"] = df["% Change"].astype(str)

# Move columns
cols_order = ["Symbol", "LTP", "% Change"] + [col for col in df.columns if col not in ["Symbol", "LTP", "% Change"]]
df = df[cols_order]

# Sort
df = df.sort_values(by=sort_col, ascending=sort_order)

# Display
st.dataframe(df, use_container_width=True)

# Download Excel
buffer = BytesIO()
df.to_excel(buffer, index=False)
st.download_button("📥 Download Excel", buffer.getvalue(), "stock_rankings.xlsx")
