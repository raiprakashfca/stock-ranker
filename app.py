import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from kiteconnect import KiteConnect
from datetime import datetime
import matplotlib.pyplot as plt
import pandas_ta as ta
from fpdf import FPDF
import base64
import os
import time
from streamlit_autorefresh import st_autorefresh
from fetch_ohlc import fetch_ohlc_data, calculate_indicators
import streamlit.components.v1 as components

st.set_page_config(page_title="📊 TMV Stock Ranking", layout="wide")

# Setup Google credentials
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=scope
)
client = gspread.authorize(credentials)

# Load Zerodha credentials
token_sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")
api_key = token_sheet.acell("A1").value
api_secret = token_sheet.acell("B1").value
access_token = token_sheet.acell("C1").value

# Sidebar token generator
with st.sidebar.expander("🔐 Zerodha Token Generator", expanded=False):
    st.markdown(f"👉 [Login to Zerodha](https://kite.zerodha.com/connect/login?v=3&api_key={api_key})", unsafe_allow_html=True)
    request_token = st.text_input("Paste Request Token Here")
    if st.button("Generate Access Key"):
        try:
            kite = KiteConnect(api_key=api_key)
            session_data = kite.generate_session(request_token, api_secret=api_secret)
            access_token = session_data["access_token"]
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            token_sheet.update_acell("C1", access_token)
            token_sheet.update_acell("D1", timestamp)
            st.success("✅ Access Token saved successfully.")
        except Exception as e:
            st.error(f"❌ Failed to generate access token: {e}")

# Validate token before proceeding
try:
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    profile = kite.profile()
    st.sidebar.success(f"🔐 Token verified: {profile['user_name']} ({profile['user_id']})")
except Exception as e:
    st.sidebar.error(f"❌ Token verification failed: {e}")
    st.stop()

# Auto-refresh every 60 seconds
st_autorefresh(interval=60000, key="refresh")

# Countdown + Refresh above the table
countdown_html = f"""
<div style=\"font-family: monospace; font-size: 18px; background: #f8f8f8; padding: 10px; border-radius: 10px; text-align: center;\">
  🔄 Auto-refreshes every 1 minute<br>
  ⏳ <b>Next refresh in <span id=\"timer\">{60}</span> seconds</b>
</div>

<script>
  var totalSeconds = {60};
  var countdownEl = document.getElementById(\"timer\");
  var countdown = setInterval(function() {{
    totalSeconds--;
    if (totalSeconds <= 0) {{
      clearInterval(countdown);
      location.reload();
    }} else {{
      countdownEl.textContent = totalSeconds;
    }}
  }}, 1000);
</script>
"""
components.html(countdown_html, height=100)

# TMV Table & Explainer
st.title("📈 Multi-Timeframe TMV Stock Ranking Dashboard")
try:
    csv_url = "https://docs.google.com/spreadsheets/d/1Cpgj1M_ofN1SqvuqDDHuN7Gy17tfkhy4fCCP8Mx7bRI/export?format=csv&gid=0"
    df = pd.read_csv(csv_url)

    df = df[[ 
        "Symbol", "LTP", "% Change",
        "15m TMV Score", "15m Trend Direction", "15m Reversal Probability",
        "1d TMV Score", "1d Trend Direction", "1d Reversal Probability"
    ]]

    # Always add TATAPOWER if missing
    if "TATAPOWER" not in df["Symbol"].values:
        df = pd.concat([df, pd.DataFrame([{"Symbol": "TATAPOWER"}])], ignore_index=True)

    st.dataframe(df, use_container_width=True)

    st.markdown("---")
    st.subheader("📘 TMV Explainer")

    selected_stock = st.selectbox("Select a stock to generate explanation", df["Symbol"].unique())
    if selected_stock:
        st.markdown(f"### Real Indicators for {selected_stock}")
        try:
            df_15m = fetch_ohlc_data(selected_stock, "15minute", 7)
            df_1d = fetch_ohlc_data(selected_stock, "day", 90)

            ind_15m = calculate_indicators(df_15m)
            ind_1d = calculate_indicators(df_1d)

            with st.expander("📊 15m TMV Input Components (with meaning)"):
                st.markdown("### 📘 Indicator Breakdown (15m)")
                indicator_descriptions = {
                    "EMA_8": "Exponential Moving Average over 8 periods — gives more weight to recent prices. Helps detect short-term trends.",
                    "EMA_21": "Exponential Moving Average over 21 periods — used to identify medium-term trend direction.",
                    "RSI": "Relative Strength Index — momentum oscillator. Values >70 suggest overbought; <30 suggest oversold.",
                    "MACD": "Moving Average Convergence Divergence — trend-following momentum indicator. A rising MACD suggests bullish momentum.",
                    "ADX": "Average Directional Index — strength of the trend. ADX > 25 indicates a strong trend.",
                    "OBV": "On-Balance Volume — volume-based trend confirmation. Rising OBV with rising price confirms uptrend.",
                    "MFI": "Money Flow Index — RSI + volume. Measures buying/selling pressure. High = overbought, low = oversold."
                }
                for key, value in ind_15m.items():
                    desc = indicator_descriptions.get(key, "No description available.")
                    st.markdown(f"""**{key}: {round(value, 2) if isinstance(value, (float, int)) else value}**\n*{desc}*""")

            with st.expander("📊 1d TMV Input Components (with meaning)"):
                st.markdown("### 📘 Indicator Breakdown (1d)")
                for key, value in ind_1d.items():
                    desc = indicator_descriptions.get(key, "No description available.")
                    st.markdown(f"""**{key}: {round(value, 2) if isinstance(value, (float, int)) else value}**\n*{desc}*""")

            df_15m["EMA_8"] = df_15m.ta.ema(length=8)
            df_15m["EMA_21"] = df_15m.ta.ema(length=21)
            fig, ax = plt.subplots()
            ax.plot(df_15m.index, df_15m["close"], label="Close")
            ax.plot(df_15m.index, df_15m["EMA_8"], label="EMA 8")
            ax.plot(df_15m.index, df_15m["EMA_21"], label="EMA 21")
            ax.legend()
            st.pyplot(fig)

        except Exception as e:
            st.error(f"❌ Error fetching indicators for {selected_stock}: {e}")
except Exception as e:
    st.error(f"❌ Failed to load TMV data: {e}")
