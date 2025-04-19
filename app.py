import streamlit as st
import pandas as pd
from utils.zerodha import get_kite, get_stock_data
from utils.indicators import calculate_scores
from utils.sheet_logger import log_to_google_sheets
from kiteconnect import KiteConnect
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO

st.set_page_config(page_title="📊 Multi-Timeframe Stock Ranking Dashboard", layout="wide")

st.markdown("""
    <style>
    .score-badge {
        display: inline-block;
        padding: 6px 12px;
        border-radius: 12px;
        font-weight: 600;
        color: white;
    }
    .high { background-color: #28a745; }
    .medium { background-color: #ffc107; color: black; }
    .low { background-color: #dc3545; }
    .section-card {
        background-color: #f9f9f9;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    </style>
""", unsafe_allow_html=True)

st.title("📊 Multi-Timeframe Stock Ranking Dashboard")

# Authenticate from GSheet
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["gspread_service_account"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("ZerodhaTokenStore").sheet1
tokens = sheet.get_all_values()[0]

# Kite
kite = KiteConnect(api_key=tokens[0])
kite.set_access_token(tokens[2])

# Timeframes to analyze
TIMEFRAMES = {
    "15m": {"interval": "15minute", "days": 5},
    "1h": {"interval": "60minute", "days": 15},
    "1d": {"interval": "day", "days": 90},
}

symbols = ["RELIANCE", "INFY", "TCS", "ICICIBANK", "HDFCBANK", "SBIN", "BHARTIARTL"]
all_data = []

with st.spinner("🔍 Analyzing all timeframes..."):
    for symbol in symbols:
        row = {"Symbol": symbol}
        for label, config in TIMEFRAMES.items():
            df = get_stock_data(kite, symbol, config["interval"], config["days"])
            if not df.empty:
                try:
                    result = calculate_scores(df)
                    for key, value in result.items():
                        row[f"{key} ({label})"] = value
                except Exception as e:
                    st.warning(f"⚠️ {symbol} ({label}) failed: {e}")
        all_data.append(row)

if not all_data:
    st.error("❌ No stock data available.")
    st.stop()

final_df = pd.DataFrame(all_data)

# Sort + Filter UI
st.markdown("### 🔎 Filter and Sort")
sort_column = st.selectbox("Sort by", [col for col in final_df.columns if "Score" in col])
sort_asc = st.radio("Order", ["Descending", "Ascending"]) == "Ascending"
limit = st.slider("Top N Symbols", 1, len(final_df), 10)

# Badge formatting
def render_badge(score):
    try:
        score = float(score)
        if score >= 0.75:
            return f"<span class='score-badge high'>🟢 {score:.2f}</span>"
        elif score >= 0.4:
            return f"<span class='score-badge medium'>🟡 {score:.2f}</span>"
        else:
            return f"<span class='score-badge low'>🔴 {score:.2f}</span>"
    except:
        return score

score_cols = [col for col in final_df.columns if "Score" in col or "Symbol" in col]
display_df = final_df[score_cols].copy().sort_values(by=sort_column, ascending=sort_asc).head(limit).set_index("Symbol")
styled = display_df.style.format({col: render_badge for col in display_df.columns}, escape="html")

st.markdown("<div class='section-card'>", unsafe_allow_html=True)
st.markdown("### 📈 Detailed Scores (Trend / Momentum / Volume)")
st.write(styled.to_html(escape=False), unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

# Legend
st.markdown("""
#### 🟢🟡🔴 Score Legend
- 🟢 High Score (≥ 0.75) — Strong trend/momentum/volume
- 🟡 Moderate Score (0.4–0.74) — Watch closely
- 🔴 Low Score (< 0.4) — Weak signal
""")

# Explanation
with st.expander("ℹ️ How to interpret these scores"):
    st.markdown("""
    #### 🧠 Score Guide
    - **Trend Score**: Indicates direction consistency
    - **Momentum Score**: Speed of movement
    - **Volume Score**: Strength of participation

    📌 A high score in all = strong setup.  
    ⚠️ Mixed timeframe scores = wait and observe.
    """)

# Raw values
with st.expander("🧪 Raw Indicator Values"):
    for symbol in symbols:
        st.markdown(f"#### {symbol}")
        for label in TIMEFRAMES:
            keys = [
                f"EMA8 ({label})", f"EMA21 ({label})", f"MACD ({label})", f"RSI ({label})",
                f"ADX ({label})", f"OBV ({label})", f"MFI ({label})", f"SUPERT ({label})",
                f"HULL ({label})", f"ALLIGATOR ({label})", f"FAMA ({label})"
            ]
            subset = final_df[final_df.Symbol == symbol][keys].transpose().reset_index()
            subset.columns = ["Indicator", f"Value ({label})"]
            st.dataframe(subset, use_container_width=True)

# Export
excel_buffer = BytesIO()
final_df.to_excel(excel_buffer, index=False)
st.download_button("📥 Download Excel", data=excel_buffer.getvalue(), file_name="stock_rankings.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# Log
try:
    log_to_google_sheets(sheet_name="Combined", df=final_df)
    st.success("✅ Data saved to Google Sheet.")
except Exception as e:
    st.warning(f"⚠️ Sheet log failed: {e}")
