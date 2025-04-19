import streamlit as st
import pandas as pd
import datetime
from utils.zerodha import authenticate_kite, fetch_ohlcv_data
from utils.indicators import calculate_indicators
from utils.sheet_logger import log_to_sheet

# Streamlit page configuration
st.set_page_config(
    page_title="📊 Stock Ranking Dashboard",
    layout="wide"
)

# Header
st.title("📈 Multi-Timeframe Stock Ranking Dashboard")

# Sidebar: timeframe selection
st.sidebar.header("🕒 Timeframe Selection")
timeframe = st.sidebar.selectbox("Select timeframe", ["15min", "1h", "1d"])

# Define time range based on timeframe
today = datetime.datetime.now()
if timeframe == "15min":
    start = today - datetime.timedelta(days=5)
elif timeframe == "1h":
    start = today - datetime.timedelta(days=15)
else:  # 1d
    start = today - datetime.timedelta(days=90)

# Sidebar: stock selection
st.sidebar.header("📌 Select Stocks")
stock_list = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS",
    "KOTAKBANK", "LT", "SBIN", "AXISBANK", "HINDUNILVR",
    "ITC", "BHARTIARTL", "BAJFINANCE"
]
selected_stocks = st.sidebar.multiselect("Choose heavyweight stocks:", stock_list, default=stock_list)

# Validate selection
if not selected_stocks:
    st.warning("⚠️ Please select at least one stock to proceed.")
    st.stop()

# Authenticate Kite
st.sidebar.header("🔑 Zerodha Credentials")
kite = authenticate_kite()
if not kite:
    st.error("❌ Kite authentication failed. Check token or API credentials.")
    st.stop()

# Fetch and compute
@st.cache_data(ttl=300)
def fetch_and_rank_stocks(stocks, start, end, interval):
    results = []
    for stock in stocks:
        try:
            df = fetch_ohlcv_data(kite, stock, start, end, interval)
            if df.empty or len(df) < 20:
                continue
            indicators = calculate_indicators(df)
            indicators["Stock"] = stock
            results.append(indicators)
        except Exception as e:
            st.error(f"⚠️ Error processing {stock}: {str(e)}")
    return pd.DataFrame(results)

# Process and show results
with st.spinner("🔍 Analyzing data..."):
    end = datetime.datetime.now()
    rankings = fetch_and_rank_stocks(selected_stocks, start, end, timeframe)

if rankings.empty:
    st.warning("🚫 No data available for the selected timeframe or stocks.")
    st.stop()

# Sort and display
rankings = rankings.sort_values("Score", ascending=False)
st.success("✅ Analysis complete.")
st.dataframe(rankings.style.background_gradient(cmap="Greens"))

# Log to Google Sheets
if st.button("📝 Log Results to Google Sheets"):
    try:
        log_to_sheet(rankings, timeframe)
        st.success("✅ Logged to Google Sheets successfully.")
    except Exception as e:
        st.error(f"❌ Failed to log: {e}")
