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

st.set_page_config(page_title="📊 Stock Ranker Dashboard", layout="wide")
st.title("📊 Multi-Timeframe Stock Ranking Dashboard")

# 🔐 Always-visible sidebar token handler
with st.sidebar.expander("🔐 Zerodha Access Token", expanded=False):
    st.markdown("This panel lets you manage Zerodha API tokens manually if needed.")

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["gspread_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open("ZerodhaTokenStore").sheet1
    tokens = sheet.get_all_values()[0]  # A1 = API Key, B1 = Secret, C1 = Access Token

    api_key = tokens[0]
    api_secret = tokens[1]
    access_token = tokens[2]

    st.markdown(f"[🔁 Click here to login to Zerodha](https://kite.zerodha.com/connect/login?v=3&api_key={api_key})")
    request_token = st.text_input("🔑 Paste new Request Token", key="manual_token")

    if request_token:
        try:
            kite = KiteConnect(api_key=api_key)
            session_data = kite.generate_session(request_token, api_secret=api_secret)
            sheet.update_cell(1, 3, session_data["access_token"])
            st.success("✅ Access token updated successfully.")
            st.stop()
        except Exception as e:
            st.error("❌ Failed to update token. Please try again.")
            st.exception(e)

# 🧠 Setup connection to Kite API
kite = KiteConnect(api_key=tokens[0])
try:
    kite.set_access_token(tokens[2])
except Exception as e:
    st.error("⚠️ Access token invalid or expired. Use the sidebar to generate a new one.")
    st.stop()

# ⚙️ Configuration
TIMEFRAMES = {
    "15m": {"interval": "15minute", "days": 5},
    "1h": {"interval": "60minute", "days": 15},
    "1d": {"interval": "day", "days": 90},
}
SYMBOLS = ["RELIANCE", "TCS", "INFY", "ICICIBANK", "HDFCBANK", "SBIN", "BHARTIARTL"]

# 📊 Fetch & Analyze
all_data = []
with st.spinner("🔄 Fetching and scoring data..."):
    for symbol in SYMBOLS:
        row = {"Symbol": symbol}
        for label, config in TIMEFRAMES.items():
            df = get_stock_data(kite, symbol, config["interval"], config["days"])
            if df.empty:
                st.warning(f"⚠️ No data for {symbol} [{label}]")
                continue
            try:
                result = calculate_scores(df)
                for key, value in result.items():
                    row[f"{key} ({label})"] = value
            except Exception as e:
                st.warning(f"⚠️ Failed scoring {symbol} [{label}]: {e}")
        all_data.append(row)

# 🪄 Compile & Display
if all_data:
    df = pd.DataFrame(all_data)
    st.dataframe(df, use_container_width=True)

    # 💾 Export
    excel_buffer = BytesIO()
    df.to_excel(excel_buffer, index=False)
    st.download_button("📥 Download Excel", data=excel_buffer.getvalue(), file_name="stock_rankings.xlsx")

    # 📤 Sheet sync
    try:
        log_to_google_sheets("Combined", df)
        st.success("✅ Logged to Google Sheet")
    except Exception as e:
        st.warning(f"⚠️ Sheet
