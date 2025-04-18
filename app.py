import streamlit as st
import pandas as pd
from utils.zerodha import get_kite, get_stock_data
from utils.indicators import calculate_scores
from utils.sheet_logger import log_to_google_sheets

st.set_page_config(page_title="📊 Multi-Timeframe Stock Ranking Dashboard", layout="wide")
st.title("📊 Multi-Timeframe Stock Ranking Dashboard")

kite = get_kite()

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
