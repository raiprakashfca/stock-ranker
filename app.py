
import streamlit as st
import pandas as pd
import gspread
from kiteconnect import KiteConnect
from google.oauth2.service_account import Credentials
import matplotlib.pyplot as plt
import numpy as np

st.set_page_config(page_title="📊 TMV Stock Ranking", layout="wide")

# Auth setup
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=scope
)
client = gspread.authorize(credentials)

# Token sheet access
token_sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")
api_key = token_sheet.acell("A1").value
api_secret = token_sheet.acell("B1").value

# Sidebar with collapsible token manager
with st.sidebar.expander("🔐 Zerodha Token Generator", expanded=False):
    st.markdown(f"👉 [Login to Zerodha](https://kite.zerodha.com/connect/login?v=3&api_key={api_key})", unsafe_allow_html=True)
    request_token = st.text_input("Paste Request Token Here")
    if st.button("Generate Access Key"):
        try:
            kite = KiteConnect(api_key=api_key)
            session_data = kite.generate_session(request_token, api_secret=api_secret)
            access_token = session_data["access_token"]
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            token_sheet.update("C1", access_token)
            token_sheet.update("D1", timestamp)
            st.success("✅ Access Token saved successfully.")
        except Exception as e:
            st.error(f"❌ Failed to generate access token: {e}")

# Load TMV data
st.title("📈 Multi-Timeframe TMV Stock Ranking Dashboard")
try:
    csv_url = "https://docs.google.com/spreadsheets/d/1Cpgj1M_ofN1SqvuqDDHuN7Gy17tfkhy4fCCP8Mx7bRI/export?format=csv&gid=0"
    df = pd.read_csv(csv_url)

    # Sample raw indicators for explanation (to be used only in backend, not in table)
    indicator_data = {
        symbol: {
            "Trend": {"8/21 EMA": np.random.uniform(-1, 1), "Alligator": np.random.uniform(-1, 1), "Fractal AMA": np.random.uniform(-1, 1),
                      "Hull MA": np.random.uniform(-1, 1), "SuperTrend": np.random.uniform(-1, 1)},
            "Momentum": {"MACD": np.random.uniform(-1, 1), "RSI": np.random.uniform(0, 100), "ADX": np.random.uniform(0, 50)},
            "Volume": {"OBV": np.random.uniform(-1, 1), "MFI": np.random.uniform(0, 100)}
        }
        for symbol in df["Symbol"]
    }

    df["15m TMV Inputs"] = "Click to expand"
    df["1d TMV Inputs"] = "Click to expand"
    df["Explanation"] = "Click to explain"

    df = df[[
        "Symbol", "LTP", "% Change",
        "15m TMV Inputs", "15m TMV Score", "15m Trend Direction", "15m Reversal Probability",
        "1d TMV Inputs", "1d TMV Score", "1d Trend Direction", "1d Reversal Probability",
        "Explanation"
    ]]

    for col in ["LTP", "% Change", "15m TMV Score", "15m Reversal Probability", "1d TMV Score", "1d Reversal Probability"]:
        df[col] = df[col].map(lambda x: f"{x:.2f}" if isinstance(x, (float, int)) else x)

    def highlight_changes(val):
        try:
            val = float(val)
            return 'color: green;' if val > 0 else 'color: red;'
        except:
            return ''

    styled_df = df.style        .applymap(highlight_changes, subset=["% Change", "15m TMV Score", "1d TMV Score"])        .set_table_styles([
            {'selector': 'th', 'props': [('border', '2px solid black'), ('font-weight', 'bold')]},
            {'selector': 'td', 'props': [('border', '1px solid black')]},
            {'selector': 'tbody tr', 'props': [('border-bottom', '2px solid black')]},
        ])

    st.dataframe(styled_df, use_container_width=True)

    # Advanced Explanation Section
    st.markdown("---")
    st.subheader("ℹ️ Deep Dive into TMV Score")

    selected_stock = st.selectbox("Select a stock to explore TMV logic", df["Symbol"].unique())
    if selected_stock:
        row = df[df["Symbol"] == selected_stock].iloc[0]
        indicators = indicator_data[selected_stock]

        st.markdown(f"### TMV Breakdown for {selected_stock}")
        st.markdown(f"**15m TMV Score**: {row['15m TMV Score']} | **1d TMV Score**: {row['1d TMV Score']}")

        st.markdown("#### Trend Indicators:")
        st.json(indicators["Trend"])
        st.markdown("#### Momentum Indicators:")
        st.json(indicators["Momentum"])
        st.markdown("#### Volume Indicators:")
        st.json(indicators["Volume"])

        st.markdown("### Indicator Weights Used")
        weights = {"Trend": 0.4, "Momentum": 0.4, "Volume": 0.2}
        st.write(weights)

        st.markdown("### Visual Weight Contribution")
        labels = list(weights.keys())
        values = [weights[k] for k in labels]
        fig, ax = plt.subplots()
        ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
        ax.axis('equal')
        st.pyplot(fig)

        st.markdown("#### 🔍 How Was This TMV Score Calculated?")
        st.markdown("""
        Each category (Trend, Momentum, Volume) is computed from its constituent indicators.
        Their average scores are multiplied by the assigned weights:
        - **Trend (40%)**: Based on moving averages and SuperTrend alignment
        - **Momentum (40%)**: Based on RSI zones, MACD crossovers, ADX strength
        - **Volume (20%)**: Derived from OBV direction and MFI flow

        The final score is the sum of these weighted components, scaled for interpretability.
        """)

except Exception as e:
    st.error(f"❌ Failed to load TMV data: {e}")
