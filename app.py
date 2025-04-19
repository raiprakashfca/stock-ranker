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
    styles = {
        "Bullish": ("🟢 Bullish", "bullish"),
        "Bearish": ("🔴 Bearish", "bearish"),
        "Neutral": ("🟡 Neutral", "neutral")
    }
    emoji, css_class = styles.get(label, ("❓", "neutral"))
    return f"<span class='direction {css_class}'>{emoji}</span>"

# Helper for reversal probability
def reversal_indicator(prob):
    try:
        prob = float(prob)
        if prob >= 0.7:
            return f"<span class='score-badge high'>🔄 {prob:.2f}</span>"
        elif prob >= 0.4:
            return f"<span class='score-badge medium'>➖ {prob:.2f}</span>"
        else:
            return f"<span class='score-badge low'>✅ {prob:.2f}</span>"
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
                    default_keys = ["Trend Score", "Momentum Score", "Volume Score", "Total Score", "Trend Direction", "Reversal Probability"]
                    for key in default_keys:
                        if key not in result:
                            result[key] = "N/A" if "Direction" in key else 0.0
                    st.sidebar.write(f"📊 {symbol} [{label}]", result)
                    adjusted_result = {}
                    for key, value in result.items():
                        adjusted_key = "TMV Score" if key == "Total Score" else key
                        adjusted_result[adjusted_key] = value
                        colname = f"{adjusted_key} ({label})"
                        row[colname] = value
                except Exception as e:
                    st.warning(f"⚠️ {symbol} ({label}) failed: {e}")
        all_data.append(row)

if not all_data:
    st.error("❌ No stock data available.")
    st.stop()

final_df = pd.DataFrame(all_data)
st.sidebar.write("✅ Final DF Columns", final_df.columns.tolist())

st.markdown("### 🔎 Filter and Sort")
sort_column = st.selectbox("Sort by", [col for col in final_df.columns if "Score" in col or "Reversal Probability" in col])
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

score_cols = [col for col in final_df.columns if any(x in col for x in ["TMV Score", "Trend Direction", "Reversal Probability", "Symbol"]) ]
detailed_cols = [col for col in final_df.columns if any(x in col for x in ["Trend Score", "Momentum Score", "Volume Score"])]
display_df = final_df[score_cols].copy()

# Remove previous separator column logic — now handled via grouping only
# No need to insert manual separator columns

# Sort and index
display_df = display_df.sort_values(by=sort_column, ascending=sort_asc).head(limit)

new_cols = []
for col in display_df.columns:
    if col == "Symbol":
        new_cols.append(("Meta", "Symbol"))
    elif "(" in col and ")" in col:
        try:
            base, tf = col.rsplit(" (", 1)
            tf = tf.replace(")", "")
            new_cols.append((tf, base))
        except:
            new_cols.append(("Other", col))
    else:
        new_cols.append(("Other", col))
display_df.columns = pd.MultiIndex.from_tuples(new_cols)
display_df = display_df.set_index(("Meta", "Symbol"))

def generate_custom_table(df):
    html = "<table style='width:100%; border-collapse:collapse;'>"
    html += "<thead><tr><th>Symbol</th>"
    for timeframe in TIMEFRAMES:
        for metric in ["TMV Score", "Trend Direction", "Reversal Probability"]:
            html += f"<th>{metric} ({timeframe})</th>"
    html += "</tr></thead><tbody>"
    for symbol in df.index:
        html += f"<tr><td><b>{symbol}</b></td>"
        for timeframe in TIMEFRAMES:
            for metric in ["TMV Score", "Trend Direction", "Reversal Probability"]:
                try:
                    val = df.loc[symbol, (timeframe, metric)]
                except:
                    val = ""

                if "Score" in metric:
                    html += f"<td>{render_badge(val)}</td>"
                elif "Reversal" in metric:
                    html += f"<td>{reversal_indicator(val)}</td>"
                elif "Direction" in metric:
                    html += f"<td>{trend_direction_emoji(val)}</td>"
                else:
                    html += f"<td>{val}</td>"
        html += "</tr>"
    html += "</tbody></table>"
    return html

st.markdown(generate_custom_table(display_df), unsafe_allow_html=True)



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
from datetime import datetime
now = datetime.now().strftime("%Y-%m-%d_%H%M")
st.caption(f"🕒 Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.download_button("📥 Download Excel", data=excel_buffer.getvalue(), file_name="stock_rankings.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

try:
    log_to_google_sheets(sheet_name="Combined", df=final_df)
    st.success("✅ Data saved to Google Sheet.")
except Exception as e:
    st.error("Google Sheet sync failed. Please re-authenticate or check sheet name.")
    st.exception(e)
