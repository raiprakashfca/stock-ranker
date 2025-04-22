import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from kiteconnect import KiteConnect
import datetime

st.set_page_config(page_title="📊 TMV Stock Ranking", layout="wide")

# Sidebar: Zerodha Login and Token Input
st.sidebar.markdown("## 🔐 Zerodha Access Token Setup")

# Load API credentials from Google Sheet
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("gcreds.json", scope)
client = gspread.authorize(creds)
sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")

api_key = sheet.acell("A1").value
api_secret = sheet.acell("B1").value
login_url = f"https://kite.zerodha.com/connect/login?v=3&api_key={api_key}"

st.sidebar.markdown(f"[🔗 Login to Zerodha]({login_url})", unsafe_allow_html=True)
request_token = st.sidebar.text_input("Paste Request Token Here")

if st.sidebar.button("Generate Access Key"):
    try:
        kite = KiteConnect(api_key=api_key)
        data = kite.generate_session(request_token, api_secret=api_secret)
        access_token = data["access_token"]
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.update_acell("C1", access_token)
        sheet.update_acell("D1", timestamp)
        st.sidebar.success("✅ Access Token Saved Successfully!")
    except Exception as e:
        st.sidebar.error(f"❌ Failed to generate access token: {e}")

# Load Background Analysis data
st.title("📈 Multi-Timeframe TMV Stock Ranking Dashboard")
try:
    sheet_url = "https://docs.google.com/spreadsheets/d/your-sheet-id/edit#gid=0"
    csv_export_url = sheet_url.replace("/edit#gid=", "/export?format=csv&gid=")
    df = pd.read_csv(csv_export_url)

    df = df[[
        "Symbol", "LTP", "% Change",
        "15m TMV Score", "15m Trend Direction", "15m Reversal Probability",
        "1d TMV Score", "1d Trend Direction", "1d Reversal Probability"
    ]]

    # Enhanced Styling
    def highlight_vals(val):
        if isinstance(val, (float, int)):
            return "color: green" if val > 0 else "color: red"
        return ""

    styled_df = df.style.applymap(highlight_vals, subset=["% Change", "15m TMV Score", "1d TMV Score"])
    st.dataframe(styled_df, use_container_width=True)
except Exception as e:
    st.error(f"Failed to load data from Google Sheet: {e}")
