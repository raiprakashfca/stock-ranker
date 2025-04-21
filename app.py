import json
import pandas as pd
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO
from utils.zerodha import get_kite, get_stock_data
from utils.indicators import calculate_scores
from utils.sheet_logger import log_to_google_sheets

st.set_page_config(page_title="📊 Multi-Timeframe Stock Ranking Dashboard", layout="wide")

# Auto refresh every minute
st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)

st.markdown("""
<style>
th, td { border-right: 1px solid #ddd; }
.score-badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 8px;
    font-weight: bold;
    min-width: 80px;
    text-align: center;
}
.high { background-color: #28a745; color: white; }
.medium { background-color: #ffc107; color: black; }
.low { background-color: #dc3545; color: white; }
.direction { font-weight: bold; padding: 2px 6px; border-radius: 6px; margin-left: 6px; }
.bullish { background-color: #c6f6d5; color: #22543d; }
.bearish { background-color: #fed7d7; color: #742a2a; }
.neutral { background-color: #fff3cd; color: #856404; }
th:first-child, td:first-child {
  position: sticky;
  left: 0;
  background-color: #2a2a2a;
  z-index: 2;
  color: #fff;
  font-weight: bold;
}
</style>
""", unsafe_allow_html=True)

st.title("📊 Multi-Timeframe Stock Ranking Dashboard")

# Load credentials
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["gspread_service_account"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Read live LTPs
ltp_sheet = client.open("LiveLTPStore").sheet1
ltp_data = pd.DataFrame(ltp_sheet.get_all_records())

# Read Zerodha credentials
token_sheet = client.open("ZerodhaTokenStore").sheet1
tokens = token_sheet.get_all_values()[0]
api_key, api_secret, access_token = tokens[0], tokens[1], tokens[2]

# Initialize Kite
kite = get_kite(api_key, access_token)

TIMEFRAMES = {
    "15m": {"interval": "15minute", "days": 5},
    "1h": {"interval": "60minute", "days": 15},
    "1d": {"interval": "day", "days": 90},
}

symbols = ltp_data["Symbol"].tolist()
all_data = []

with st.spinner("🔍 Analyzing all timeframes..."):
    for symbol in symbols:
        row = {"Symbol": symbol}
        live_row = ltp_data[ltp_data["Symbol"] == symbol]
        if not live_row.empty:
            row["LTP"] = float(live_row.iloc[0]["LTP"])
        for label, config in TIMEFRAMES.items():
            df = get_stock_data(kite, symbol, config["interval"], config["days"])
            if not df.empty:
                try:
                    result = calculate_scores(df)
                    if label == "1d":
                        row["Close (Prev Day)"] = float(df.iloc[-2]["close"])
                    for key, value in result.items():
                        adjusted_key = "TMV Score" if key == "Total Score" else key
                        row[f"{label} | {adjusted_key}"] = value
                except Exception as e:
                    st.warning(f"⚠️ {symbol} ({label}) failed: {e}")
        all_data.append(row)

if not all_data:
    st.error("❌ No stock data available.")
    st.stop()

final_df = pd.DataFrame(all_data)

# % Change from yesterday's close
final_df["% Change"] = final_df.apply(
    lambda row: f"{((row['LTP'] - row['Close (Prev Day)']) / row['Close (Prev Day)'] * 100):.2f}%" if row["Close (Prev Day)"] else "N/A", axis=1
)

# Display filtered and sorted
sort_column = st.selectbox("Sort by", [col for col in final_df.columns if "Score" in col or "Reversal" in col])
sort_asc = st.radio("Order", ["Descending", "Ascending"]) == "Ascending"
limit = st.slider("Top N Symbols", 1, len(final_df), 10)

final_df = final_df.sort_values(by=sort_column, ascending=sort_asc).head(limit)

# Highlight logic
highlight_conditions = (
    (final_df[["15m | Trend Direction", "1h | Trend Direction", "1d | Trend Direction"]] == "Bullish").all(axis=1) &
    (final_df[["15m | TMV Score", "1h | TMV Score", "1d | TMV Score"]] >= 0.8).all(axis=1)
)
highlight_red = (
    (final_df[["15m | Trend Direction", "1h | Trend Direction", "1d | Trend Direction"]] == "Bearish").all(axis=1) &
    (final_df[["15m | TMV Score", "1h | TMV Score", "1d | TMV Score"]] >= 0.8).all(axis=1)
)

def highlight_row(row):
    if highlight_conditions.loc[row.name]:
        return ["background-color: #d4edda"] * len(row)
    elif highlight_red.loc[row.name]:
        return ["background-color: #f8d7da"] * len(row)
    else:
        return [""] * len(row)

styled_df = final_df.style.apply(highlight_row, axis=1)
st.dataframe(styled_df, use_container_width=True, hide_index=False)

# Export to Excel
excel_buffer = BytesIO()
final_df.to_excel(excel_buffer, index=False)
st.download_button("📥 Download Excel", data=excel_buffer.getvalue(), file_name="stock_rankings.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

try:
    log_to_google_sheets(sheet_name="Combined", df=final_df)
    st.success("✅ Data saved to Google Sheet.")
except Exception as e:
    st.warning(f"⚠️ Could not update Google Sheet: {e}")
