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
    th, td { border-right: 1px solid #ddd; }
    .timeframe-group td:not(:first-child) {
        border-left: 3px solid #9e9e9e;
    }

    .score-badge {
        display: inline-block;
        padding: 6px 12px;
        border-radius: 12px;
        font-weight: 600;
        min-width: 100px;
        text-align: center;
    }
    .high { background-color: #28a745; }
    .medium { background-color: #ffc107; color: black; }
    .low { background-color: #dc3545; }
    .direction { font-weight: 600; padding: 2px 6px; border-radius: 8px; margin-left: 8px; }
    .bullish { background-color: #c6f6d5; color: #22543d; }
    .bearish { background-color: #fed7d7; color: #742a2a; }
    .neutral { background-color: #fff3cd; color: #856404; }
    </style>
""", unsafe_allow_html=True)

st.title("📊 Multi-Timeframe Stock Ranking Dashboard")

# Helper for trend direction
def trend_direction_emoji(label):
    return {
        "Bullish": "🟢 Bullish",
        "Bearish": "🔴 Bearish",
        "Neutral": "🟡 Neutral"
    }.get(label, "❓")

# Helper for reversal probability
def reversal_indicator(prob):
    try:
        prob = float(prob)
        if prob >= 0.7:
            return f"🔄 {prob:.2f}"
        elif prob >= 0.4:
            return f"➖ {prob:.2f}"
        else:
            return f"✅ {prob:.2f}"
    except:
        return prob

# Authenticate from GSheet
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["gspread_service_account"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("ZerodhaTokenStore").sheet1
tokens = sheet.get_all_values()[0]

kite = KiteConnect(api_key=tokens[0])
kite.set_access_token(tokens[2])

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

st.markdown("### 🔎 Filter and Sort")
sort_column = st.selectbox("Sort by", [col for col in final_df.columns if "Score" in col])
sort_asc = st.radio("Order", ["Descending", "Ascending"]) == "Ascending"
limit = st.slider("Top N Symbols", 1, len(final_df), 10)

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

score_cols = [col for col in final_df.columns if "Score" in col or "Symbol" in col or "Trend Direction" in col or "Reversal Probability" in col]
display_df = final_df[score_cols].copy()

# Remove previous separator column logic — now handled via grouping only
# No need to insert manual separator columns

# Sort and index
display_df = display_df.sort_values(by=sort_column, ascending=sort_asc).head(limit)

display_df.columns = pd.MultiIndex.from_tuples([
    ("Meta", "Symbol") if col == "Symbol" else
    (tf, col.replace(f" ({tf})", ""))
    for col in display_df.columns
    for tf in TIMEFRAMES if f"({tf})" in col
])
display_df = display_df.set_index(("Meta", "Symbol"))

styled = display_df.style.format({
    col: (
        render_badge if "Score" in col else
        trend_direction_emoji if "Trend Direction" in col else
        reversal_indicator if "Reversal Probability" in col else
        None
    ) for col in display_df.columns
}, escape="html")

st.markdown("<div class='section-card'>", unsafe_allow_html=True)
st.markdown("### 📈 Detailed Scores (Trend / Momentum / Volume + Direction + Reversal)")
st.markdown('<div style="overflow-x: auto;"><style>th:first-child, td:first-child { position: sticky; left: 0; background-color: #f9f9f9; z-index: 1; }</style>' + styled.to_html(escape=False) + '</div>', unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("""
#### 🟢🟡🔴 Score Legend
- 🟢 High Score (≥ 0.75) — Strong trend/momentum/volume
- 🟡 Moderate Score (0.4–0.74) — Watch closely
- 🔴 Low Score (< 0.4) — Weak signal

#### 🔄 Trend Direction
- 🟢 Bullish — Uptrend
- 🔴 Bearish — Downtrend
- 🟡 Neutral — Sideways/No direction

#### 🔁 Reversal Probability
- 🔄 > 0.70 = Likely reversal
- ➖ 0.40–0.70 = Uncertain
- ✅ < 0.40 = Trend continuation
""")

# Export Excel
excel_buffer = BytesIO()
final_df.to_excel(excel_buffer, index=False)
st.download_button("📥 Download Excel", data=excel_buffer.getvalue(), file_name="stock_rankings.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

try:
    log_to_google_sheets(sheet_name="Combined", df=final_df)
    st.success("✅ Data saved to Google Sheet.")
except Exception as e:
    st.warning(f"⚠️ Sheet log failed: {e}")
