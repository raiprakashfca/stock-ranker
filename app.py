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

# Fetch and compute indicator data
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

# Analyze and rank stocks
with st.spinner("🔍 Analyzing data..."):
    end = datetime.datetime.now()
    rankings = fetch_and_rank_stocks(selected_stocks, start, end, timeframe)

if rankings.empty:
    st.warning("🚫 No data available for the selected timeframe or stocks.")
    st.stop()

# Add Trend Direction and Reversal Probability
def interpret_trend(row):
    if row["Trend_Score"] == 3:
        return "Strong Uptrend"
    elif row["Trend_Score"] == 2:
        return "Moderate Uptrend"
    elif row["Trend_Score"] == 1:
        return "Weak / Sideways"
    else:
        return "Downtrend"

rankings["Trend_Direction"] = rankings.apply(interpret_trend, axis=1)
rankings["Reversal_Probability (%)"] = rankings["Reversal_Probability"].round(2)

# Sort by overall Score
rankings = rankings.sort_values("Score", ascending=False)

# Display full ranked table
st.success("✅ Analysis complete.")
st.subheader("📊 Ranked Stocks with Technical Scores")

st.dataframe(
    rankings[
        ["Stock", "Score", "Trend_Score", "Momentum_Score", "Volume_Score",
         "Trend_Direction", "Reversal_Probability (%)"]
    ].reset_index(drop=True).style.background_gradient(cmap="Greens", subset=["Score"])
)

# Display trend and reversal filter
st.subheader("⚠️ Potential Trend Reversals")

threshold = st.slider("Set minimum reversal probability %", 50, 100, 70)
high_reversal = rankings[rankings["Reversal_Probability (%)"] >= threshold]

if high_reversal.empty:
    st.info("No stocks above selected reversal probability.")
else:
    st.dataframe(
        high_reversal[
            ["Stock", "Trend_Direction", "Reversal_Probability (%)"]
        ].sort_values("Reversal_Probability (%)", ascending=False).reset_index(drop=True)
    )

# Button to log to Google Sheets
if st.button("📝 Log Results to Google Sheets"):
    try:
        log_to_sheet(rankings, timeframe)
        st.success("✅ Logged to Google Sheets successfully.")
    except Exception as e:
        st.error(f"❌ Failed to log: {e}")
