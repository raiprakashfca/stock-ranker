
import streamlit as st
import pandas as pd
import gspread
from kiteconnect import KiteConnect
from datetime import datetime
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="📊 TMV Stock Ranking", layout="wide")

# Use updated Google Auth method to avoid FileNotFoundError
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=scope
)
client = gspread.authorize(credentials)

# Access API Key, Secret, and Token Sheet
token_sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")
api_key = token_sheet.acell("A1").value
api_secret = token_sheet.acell("B1").value

# --- Sidebar with collapsible section ---
with st.sidebar.expander("🔐 Zerodha Token Generator", expanded=False):
    st.markdown(f"👉 [Login to Zerodha](https://kite.zerodha.com/connect/login?v=3&api_key={api_key})", unsafe_allow_html=True)
    request_token = st.text_input("Paste Request Token Here")
    if st.button("Generate Access Key"):
        try:
            kite = KiteConnect(api_key=api_key)
            session_data = kite.generate_session(request_token, api_secret=api_secret)
            access_token = session_data["access_token"]
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            token_sheet.update("C1", access_token)
            token_sheet.update("D1", timestamp)
            st.success("✅ Access Token saved successfully.")
        except Exception as e:
            st.error(f"❌ Failed to generate access token: {e}")

# --- Main Dashboard ---
st.title("📈 Multi-Timeframe TMV Stock Ranking Dashboard")

try:
    # Fixed export URL from provided Google Sheet
    csv_url = "https://docs.google.com/spreadsheets/d/1Cpgj1M_ofN1SqvuqDDHuN7Gy17tfkhy4fCCP8Mx7bRI/export?format=csv&gid=0"
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
