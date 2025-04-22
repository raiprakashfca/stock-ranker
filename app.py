
import json
import pandas as pd
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO
from datetime import datetime
import pytz

st.set_page_config(page_title="📊 Multi-Timeframe Stock Ranking Dashboard", layout="wide")

# Sidebar with login and token management
st.sidebar.title("🔐 Zerodha API Login")
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["gspread_service_account"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
token_sheet = client.open("ZerodhaTokenStore").sheet1

api_key = token_sheet.cell(1, 1).value
api_secret = token_sheet.cell(1, 2).value

st.sidebar.text_input("API Key", value=api_key, key="api_key", disabled=True)
st.sidebar.text_input("API Secret", value=api_secret, key="api_secret", disabled=True)

redirect_url = "https://stock-ranker-prakash.streamlit.app/"
login_url = f"https://kite.trade/connect/login?api_key={api_key}&v=3&redirect_uri={redirect_url}"
st.sidebar.markdown(f"[🟢 Click here to login to Zerodha]({login_url})", unsafe_allow_html=True)

access_code = st.sidebar.text_input("🔑 Paste Access Code", type="password")
if st.sidebar.button("Generate Token"):
    from kiteconnect import KiteConnect
    kite = KiteConnect(api_key=api_key)
    data = kite.generate_session(access_code, api_secret=api_secret)
    access_token = data["access_token"]
    token_sheet.update("A1", [[api_key]])
    token_sheet.update("B1", [[api_secret]])
    token_sheet.update("C1", [[access_token]])

    # ✅ Update timestamp in D1
    ist = pytz.timezone("Asia/Kolkata")
    timestamp = datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S")
    token_sheet.update("D1", [[timestamp]])

    st.sidebar.success("✅ Token Generated and Saved! Please refresh app.")

st.sidebar.markdown("---")
st.sidebar.info("📅 Timestamp updates on every token refresh.

Use the login above when token expires.")

# Main placeholder
st.title("📊 Multi-Timeframe Stock Ranking Dashboard")
st.write("✅ Sidebar now updates Zerodha token timestamp in D1 on each login.")
