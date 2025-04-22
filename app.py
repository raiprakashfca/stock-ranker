import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from kiteconnect import KiteConnect
from datetime import datetime

st.set_page_config(page_title="📊 TMV Stock Ranking", layout="wide")

# Setup Google Sheets connection
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("gcreds.json", scope)
client = gspread.authorize(creds)

# Access ZerodhaTokenStore > Sheet1
token_sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")
api_key = token_sheet.acell("A1").value
api_secret = token_sheet.acell("B1").value

# Sidebar layout
st.sidebar.markdown("## 🔐 Zerodha Access Token Setup")

# 1. Zerodha login link
login_url = f"https://kite.zerodha.com/connect/login?v=3&api_key={api_key}"
st.sidebar.markdown(f"👉 [Login to Zerodha]({login_url})", unsafe_allow_html=True)

# 2. Input box for Request Token
request_token = st.sidebar.text_input("Paste Request Token Here")

# 3. Button to generate and store access token
if st.sidebar.button("Generate Access Key"):
    try:
        kite = KiteConnect(api_key=api_key)
        session_data = kite.generate_session(request_token, api_secret=api_secret)
        access_token = session_data["access_token"]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        token_sheet.update("C1", access_token)
        token_sheet.update("D1", timestamp)
        st.sidebar.success("✅ Access Token saved successfully.")
    except Exception as e:
        st.sidebar.error(f"❌ Failed to generate access token: {e}")

# Main Dashboard UI
st.title("📈 Multi-Timeframe TMV Stock Ranking Dashboard")

try:
    sheet_url = "https://docs.google.com/spreadsheets/d/your-sheet-id/edit#gid=0"
    csv_url = sheet_url.replace("/edit#gid=", "/export?format=csv&gid=")
    df = pd.read_csv(csv_url)

    required_columns = [
        "Symbol", "LTP", "% Change",
        "15m TMV Score", "15m Trend Direction", "15m Reversal Probability",
        "1d TMV Score", "1d Trend Direction", "1d Reversal Probability"
    ]
    df = df[required_columns]

    def highlight_changes(val):
        if isinstance(val, (int, float)):
            return 'color: green' if val > 0 else 'color: red'
        return ''

    styled_df = df.style.applymap(highlight_changes, subset=["% Change", "15m TMV Score", "1d TMV Score"])
    st.dataframe(styled_df, use_container_width=True)

except Exception as e:
    st.error(f"❌ Failed to load TMV data: {e}")
