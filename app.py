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
st.title("📊 Multi-Timeframe Stock Ranking Dashboard")

# Zerodha login panel
st.sidebar.header("🔐 Zerodha Login")
api_key_input = st.sidebar.text_input("API Key")
api_secret_input = st.sidebar.text_input("API Secret", type="password")
request_token_input = st.sidebar.text_input("Paste Request Token")

kite = None
if api_key_input and api_secret_input:
    kite = KiteConnect(api_key=api_key_input)
    login_url = kite.login_url()
    st.sidebar.markdown(f"[🔑 Click here to generate Request Token]({login_url})")

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
            st.sidebar.success("✅ Token saved. Please refresh the app.")
            st.stop()
        except Exception as e:
            st.sidebar.error(f"❌ Failed to generate token: {e}")
            st.stop()
else:
    st.sidebar.info("Enter API Key & Secret to begin")
    st.stop()

# Proceed if kite is ready
TIMEFRAMES = {
    "15min": {"interval": "15minute", "days": 5},
    "1h": {"interval": "60minute", "days": 15},
    "1d": {"interval": "day", "days": 90},
}

symbols = ["RELIANCE", "INFY", "TCS", "ICICIBANK", "HDFCBANK", "SBIN", "BHARTIARTL"]
selected_timeframe = st.selectbox("Choose Timeframe", list(TIMEFRAMES.keys()))
config = TIMEFRAMES[selected_timeframe]

results = []
with st.spinner(f"🔄 Fetching and analyzing data for {selected_timeframe}..."):
    for symbol in symbols:
        df = get_stock_data(kite, symbol, config["interval"], config["days"])
        if not df.empty:
            try:
                score_row = calculate_scores(df)
                score_row["Symbol"] = symbol
                results.append(score_row)
            except Exception as e:
                st.warning(f"⚠️ Scoring failed for {symbol}: {e}")

if not results:
    st.error("❌ No valid data to display. Check data fetch or indicator logic.")
    st.stop()

df_result = pd.DataFrame(results)

if "Total Score" not in df_result.columns:
    st.error("❌ Missing 'Total Score' column. Here is the raw output:")
    st.dataframe(df_result)
    st.stop()

try:
    sorted_df = df_result.sort_values(by="Total Score", ascending=False).reset_index(drop=True)
    st.dataframe(sorted_df.style.format("{:.2f}"))
    log_to_google_sheets(sheet_name=selected_timeframe, df=sorted_df)
    st.success("✅ Logged to Google Sheet successfully!")
except KeyError as ke:
    st.error(f"❌ Sorting failed due to missing column: {ke}")
    st.dataframe(df_result)
