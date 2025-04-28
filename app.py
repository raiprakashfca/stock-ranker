import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from kiteconnect import KiteConnect
import pytz
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
            timestamp = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%Y-%m-%d %H:%M:%S")
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

st.sidebar.markdown("---")
st.sidebar.info("🔄 Data auto-refreshes every 1 minute.\n\n🕒 Last updated time shown on dashboard.")

# Auto-refresh every 60 seconds
st_autorefresh(interval=60000, key="refresh")

# Countdown + Refresh above the table
countdown_html = f"""
<div style=\"font-family: monospace; font-size: 16px; background: #e0f7fa; padding: 8px; border-radius: 8px; text-align: center; margin-bottom: 10px;\">
  🔄 Auto-refresh every 1 minute |
  ⏳ <b><span id=\"timer\">{60}</span>s</b>
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
components.html(countdown_html, height=70)

# TMV Table & Explainer
st.title("📈 Multi-Timeframe TMV Stock Ranking Dashboard")

# Display Last Updated Time
now = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%d %b %Y, %I:%M %p IST")
st.markdown(f"#### 🕒 Last Updated: {now}")

try:
    csv_url = "https://docs.google.com/spreadsheets/d/1Cpgj1M_ofN1SqvuqDDHuN7Gy17tfkhy4fCCP8Mx7bRI/export?format=csv&gid=0"
    df = pd.read_csv(csv_url)

    df = df[[ 
        "Symbol", "LTP", "% Change",
        "15m TMV Score", "15m Trend Direction", "15m Reversal Probability",
        "1d TMV Score", "1d Trend Direction", "1d Reversal Probability"
    ]]

    # Safely convert % Change to numeric
    df["% Change"] = pd.to_numeric(df["% Change"], errors="coerce")

    def highlight_change(val):
        if pd.isna(val):
            return ''
        color = 'green' if val > 0 else 'red'
        return f'color: {color}'

    styled_df = df.style.applymap(highlight_change, subset=["% Change"])
    st.dataframe(styled_df, use_container_width=True)

    with st.expander("📥 Download Today's TMV Table"):
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download as CSV",
            data=csv,
            file_name=f"TMV_Stock_Ranking_{datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y%m%d')}.csv",
            mime='text/csv',
        )

    st.markdown("---")
    st.subheader("📘 TMV Explainer")

    selected_stock = st.selectbox("Select a stock to generate explanation", df["Symbol"].dropna().unique())
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

    st.markdown("---")
    st.subheader("➕ Admin: Add New Stock")

    @st.cache_data(ttl=3600)
    def load_instruments():
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)
        instruments = kite.instruments(exchange="NSE")
        df_instruments = pd.DataFrame(instruments)
        return df_instruments[["tradingsymbol", "name", "instrument_type"]]

    df_instruments = load_instruments()

    search_query = st.text_input("Search Stock Name or Symbol")
    if search_query:
        matches = df_instruments[df_instruments["tradingsymbol"].str.contains(search_query.upper()) | df_instruments["name"].str.contains(search_query, case=False)]
        if not matches.empty:
            selected_stock = st.selectbox("Select a stock to add", matches["tradingsymbol"] + " - " + matches["name"])
            if st.button("➕ Add Selected Stock to TMV Sheet"):
                try:
                    selected_symbol = selected_stock.split(" - ")[0]
                    background_sheet = client.open("BackgroundAnalysisStore").worksheet("Sheet1")
                    background_sheet.append_row([selected_symbol])
                    st.toast(f"✅ {selected_symbol} added successfully!", icon='🎯')
                    time.sleep(2)
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed to add stock: {e}")
        else:
            st.warning("🔍 No matches found. Try different keyword.")

except Exception as e:
    st.error(f"❌ Failed to load TMV data: {e}")
