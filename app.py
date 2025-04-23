
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

# Countdown + Refresh above the table
countdown_html = f"""
<div style="font-family: monospace; font-size: 18px; background: #f8f8f8; padding: 10px; border-radius: 10px; text-align: center;">
  🔄 Auto-refreshes every 5 minutes<br>
  ⏳ <b>Next refresh in <span id="timer">{300}</span> seconds</b>
</div>

<script>
  var totalSeconds = {300};
  var countdownEl = document.getElementById("timer");
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

    df["15m TMV Inputs"] = "Click to expand"
    df["1d TMV Inputs"] = "Click to expand"
    df["Explanation"] = "Click to explain"

    df = df[[
        "Symbol", "LTP", "% Change",
        "15m TMV Inputs", "15m TMV Score", "15m Trend Direction", "15m Reversal Probability",
        "1d TMV Inputs", "1d TMV Score", "1d Trend Direction", "1d Reversal Probability",
        "Explanation"
    ]]

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

            with st.expander("📊 15m TMV Input Components"):
                st.json(ind_15m)

            with st.expander("📊 1d TMV Input Components"):
                st.json(ind_1d)

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
