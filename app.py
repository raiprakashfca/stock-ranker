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
from fetch_ohlc import fetch_ohlc_data, calculate_indicators
from streamlit_autorefresh import st_autorefresh
import time

st_autorefresh(interval=60000, key="refresh")  # 60,000 ms = 1 minute

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

# Load main stock data
st.title("📈 Multi-Timeframe TMV Stock Ranking Dashboard")
try:
    csv_url = "https://docs.google.com/spreadsheets/d/1Cpgj1M_ofN1SqvuqDDHuN7Gy17tfkhy4fCCP8Mx7bRI/export?format=csv&gid=0"


# ✅ Countdown + Auto-Refresh block (OUTSIDE the try)
countdown_sec = 300
last_refresh = st.session_state.get("last_refresh_time", time.time())
next_refresh = last_refresh + countdown_sec
remaining = int(max(0, next_refresh - time.time()))
st.session_state["last_refresh_time"] = time.time()

st_autorefresh(interval=countdown_sec * 1000, key="tmv_refresh")
st.markdown("### ⏱ Auto-Refresh Countdown")
st.info(f"🔄 This table auto-refreshes every 5 minutes.\n\n⏳ **Next refresh in `{remaining}` seconds**.")

# ✅ Data load wrapped in try block
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
    
except Exception as e:
    st.error(f"❌ Failed to load TMV data: {e}")

df = pd.read_csv(csv_url)
    df["Explanation"] = "Click to explain"

    st.dataframe(df, use_container_width=True)

    st.markdown("---")
    st.subheader("📘 TMV Explainer")

    selected_stock = st.selectbox("Select a stock to generate explanation", df["Symbol"].unique())
    if selected_stock:
        st.markdown(f"### Real Indicators for {selected_stock}")
        try:
            df_15m = fetch_ohlc_data(selected_stock, "15minute", 3)
            df_1d = fetch_ohlc_data(selected_stock, "day", 30)

            ind_15m = calculate_indicators(df_15m)
            ind_1d = calculate_indicators(df_1d)

            st.markdown("#### 📊 15m Indicators")
            st.json(ind_15m)
            st.markdown("#### 📊 1d Indicators")
            st.json(ind_1d)

            df_15m["EMA_8"] = df_15m.ta.ema(length=8)
            df_15m["EMA_21"] = df_15m.ta.ema(length=21)
            fig, ax = plt.subplots()
            ax.plot(df_15m.index, df_15m["close"], label="Close")
            ax.plot(df_15m.index, df_15m["EMA_8"], label="EMA 8")
            ax.plot(df_15m.index, df_15m["EMA_21"], label="EMA 21")
            ax.legend()
            st.pyplot(fig)

            # PDF generation
            if st.button("📄 Download TMV Explanation as PDF"):
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", "B", 14)
                pdf.cell(200, 10, f"TMV Explainer: {selected_stock}", ln=True)
                pdf.set_font("Arial", "", 12)
                pdf.cell(200, 10, "15m Indicators:", ln=True)
                for k, v in ind_15m.items():
                    pdf.cell(200, 8, f"{k}: {round(v, 2)}", ln=True)
                pdf.cell(200, 10, "1d Indicators:", ln=True)
                for k, v in ind_1d.items():
                    pdf.cell(200, 8, f"{k}: {round(v, 2)}", ln=True)
                pdf.output("/mnt/data/TMV_Explainer.pdf")
                with open("/mnt/data/TMV_Explainer.pdf", "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                    href = f'<a href="data:application/pdf;base64,{b64}" download="TMV_Explainer_{selected_stock}.pdf">📥 Click here to download PDF</a>'
                    st.markdown(href, unsafe_allow_html=True)

            # Shareable link
            share_url = f"{st.secrets['app_base_url']}?symbol={selected_stock}"
            st.markdown(f"🔗 Shareable Link: [Copy and Share]({share_url})")

        except Exception as e:
            st.error(f"❌ Error fetching indicators for {selected_stock}: {e}")
except Exception as e:
    st.error(f"❌ Failed to load TMV data: {e}")
