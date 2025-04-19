import streamlit as st
import pandas as pd
from utils.zerodha import get_kite, get_stock_data
from utils.indicators import calculate_scores
from utils.sheet_logger import log_to_google_sheets
from kiteconnect import KiteConnect
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="📊 Multi-Timeframe Stock Ranking Dashboard", layout="wide")

with st.container():
    st.markdown("""
        <style>
        .main {background-color: #f5f5f5;}
        .stDataFrame {border-radius: 10px; border: 1px solid #e0e0e0;}
        </style>
        <h1 style='text-align: center; color: #333;'>📊 Multi-Timeframe Stock Ranking Dashboard</h1>
    """, unsafe_allow_html=True)

# Zerodha login panel
with st.sidebar:
    st.markdown("## 🔐 Zerodha Login")
    api_key_input = st.text_input("API Key", placeholder="Enter your API Key")
    api_secret_input = st.text_input("API Secret", type="password", placeholder="Enter your API Secret")
    request_token_input = st.text_input("Request Token", placeholder="Paste token after login")

    kite = None
    if api_key_input and api_secret_input:
        kite = KiteConnect(api_key=api_key_input)
        login_url = kite.login_url()
        st.markdown(f"[🔑 Click here to generate Request Token]({login_url})")

        if request_token_input:
            try:
                data = kite.generate_session(request_token_input, api_secret=api_secret_input)
                access_token = data["access_token"]
                kite.set_access_token(access_token)

                # Save to Google Sheet
                scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                creds_dict = json.loads(st.secrets["gspread_service_account"])
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
                client = gspread.authorize(creds)
                sheet = client.open("ZerodhaTokenStore")
                sheet.sheet1.update("A1", [[api_key_input, api_secret_input, access_token]])
                st.success("✅ Access token saved. You can now use the dashboard.")
            except Exception as e:
                st.error(f"❌ Failed to generate token: {e}")
                st.stop()
    else:
        st.info("ℹ️ Enter API Key and Secret to proceed.")
        st.stop()

# Proceed only if kite is available
if not kite:
    st.error("❌ Kite session not established.")
    st.stop()

# Multi-timeframe setup
TIMEFRAMES = {
    "15m": {"interval": "15minute", "days": 5},
    "1h": {"interval": "60minute", "days": 15},
    "1d": {"interval": "day", "days": 90},
}

symbols = ["RELIANCE", "INFY", "TCS", "ICICIBANK", "HDFCBANK", "SBIN", "BHARTIARTL"]

combined_results = []

with st.spinner("🔄 Processing all timeframes for each stock..."):
    for symbol in symbols:
        row = {"Symbol": symbol}
        for label, config in TIMEFRAMES.items():
            df = get_stock_data(kite, symbol, config["interval"], config["days"])
            if not df.empty:
                try:
                    scores = calculate_scores(df)
                    for key, val in scores.items():
                        row[f"{key} ({label})"] = val
                except Exception as e:
                    st.warning(f"⚠️ Scoring failed for {symbol} ({label}): {e}")
        combined_results.append(row)

if not combined_results:
    st.error("❌ No data returned from any timeframe.")
    st.stop()

df_combined = pd.DataFrame(combined_results)
st.markdown("### 📊 Combined Ranking Across Timeframes")
st.dataframe(df_combined.style.format("{:.2f}"), use_container_width=True)

try:
    log_to_google_sheets(sheet_name="Combined", df=df_combined)
    st.success("✅ Combined results logged to Google Sheet.")
except Exception as e:
    st.warning(f"⚠️ Failed to log to Google Sheets: {e}")
