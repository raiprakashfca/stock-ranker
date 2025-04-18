
import streamlit as st
from utils.zerodha import get_kite, get_stock_data
from utils.indicators import calculate_scores
from utils.sheet_logger import log_to_google_sheets
import pandas as pd

st.set_page_config(page_title="📊 Stock Ranker", layout="wide")
st.title("📊 Multi-Timeframe Stock Ranking Dashboard")

TIMEFRAMES = {
    "15m": {"interval": "15minute", "days": 5},
    "1h": {"interval": "60minute", "days": 15},
    "1d": {"interval": "day", "days": 90}
}

stocks = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS",
    "LT", "SBIN", "KOTAKBANK", "AXISBANK", "ITC",
    "HINDUNILVR", "BAJFINANCE", "ASIANPAINT", "HCLTECH"
]

kite = get_kite()

tab1, tab2, tab3 = st.tabs(["15 Min", "1 Hour", "1 Day"])
for tab, tf in zip([tab1, tab2, tab3], TIMEFRAMES.keys()):
    with tab:
        st.subheader(f"{tf} Ranking")
        results = []
        for symbol in stocks:
            try:
                df = get_stock_data(kite, symbol, TIMEFRAMES[tf]['interval'], TIMEFRAMES[tf]['days'])
                score = calculate_scores(df)
                results.append({"Symbol": symbol, **score})
            except Exception as e:
                st.warning(f"Error fetching {symbol}: {e}")
        df_result = pd.DataFrame(results).sort_values(by="Total Score", ascending=False)
        st.dataframe(df_result, use_container_width=True)
        log_to_google_sheets(tf, df_result)
