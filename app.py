import os
import json
import pandas as pd
import streamlit as st
import gspread
from kiteconnect import KiteConnect
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from io import BytesIO

st.set_page_config(page_title="📊 Multi-Timeframe Stock Ranking Dashboard", layout="wide")

# === Sidebar for API Token Refresh ===
st.sidebar.title("🔐 API Token Manager")
st.sidebar.info("📅 Timestamp updates on every token refresh.")

# Load Google Sheet credentials from environment variable (base64 encoded)
creds_dict = json.loads(os.environ["GSPREAD_CREDENTIALS_JSON"])
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Load token sheet
token_sheet = client.open("ZerodhaTokenStore").sheet1
api_key, api_secret, access_token = token_sheet.get_all_values()[0][:3]

# Show login link for new access token
kite = KiteConnect(api_key=api_key)
login_url = kite.login_url()
st.sidebar.markdown(f"[🔗 Click here to login and generate new token]({login_url})")
access_code = st.sidebar.text_input("Paste access code here:")
if st.sidebar.button("🎯 Generate Access Token"):
    try:
        data = kite.generate_session(access_code, api_secret=api_secret)
        access_token = data["access_token"]
        token_sheet.update("A1", [[api_key]])
        token_sheet.update("B1", [[api_secret]])
        token_sheet.update("C1", [[access_token]])
        token_sheet.update("D1", [[datetime.now().strftime("%Y-%m-%d %H:%M:%S")]])
        st.sidebar.success("✅ Token generated and stored successfully!")
    except Exception as e:
        st.sidebar.error(f"❌ Error: {e}")

# Read BackgroundAnalysisStore Sheet
sheet = client.open("BackgroundAnalysisStore").sheet1
data = pd.DataFrame(sheet.get_all_records())

if data.empty:
    st.error("❌ No data available in BackgroundAnalysisStore.")
    st.stop()

# Ensure column order for visibility
symbol_cols = ["Symbol", "LTP", "% Change"]
score_cols = [col for col in data.columns if col not in symbol_cols]
data = data[symbol_cols + score_cols]

# Sorting & Filtering
st.title("📊 Multi-Timeframe Stock Ranking Dashboard")
sort_col = st.selectbox("Sort by", score_cols)
sort_asc = st.radio("Sort order", ["Descending", "Ascending"]) == "Ascending"
limit = st.slider("Number of rows", 1, len(data), min(10, len(data)))

data = data.sort_values(by=sort_col, ascending=sort_asc).head(limit)

# Conditional Highlighting
def highlight_row(row):
    try:
        if (row["15m Trend Direction"] == "Bullish" and
            row["1d Trend Direction"] == "Bullish" and
            row["15m TMV Score"] >= 0.8 and row["1d TMV Score"] >= 0.8):
            return ["background-color: #d4edda"] * len(row)
        elif (row["15m Trend Direction"] == "Bearish" and
              row["1d Trend Direction"] == "Bearish" and
              row["15m TMV Score"] >= 0.8 and row["1d TMV Score"] >= 0.8):
            return ["background-color: #f8d7da"] * len(row)
        else:
            return [""] * len(row)
    except:
        return [""] * len(row)

st.dataframe(data.style.apply(highlight_row, axis=1), use_container_width=True)

# Excel Export
buffer = BytesIO()
data.to_excel(buffer, index=False)
st.download_button("📥 Download Excel", data=buffer.getvalue(), file_name="tmv_scores.xlsx")
