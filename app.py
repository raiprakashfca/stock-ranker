import json
import os
import pandas as pd
import streamlit as st
import gspread
from datetime import datetime
from io import BytesIO
from oauth2client.service_account import ServiceAccountCredentials
from utils.zerodha import get_kite, get_stock_data, update_ltp_sheet
from utils.indicators import calculate_scores
from utils.sheet_logger import log_to_google_sheets

st.set_page_config(page_title="📊 Multi-Timeframe Stock Ranking", layout="wide")

# Sidebar - Always visible with collapse option
with st.sidebar:
    st.header("🔐 Zerodha API Token")
    st.markdown("Use the login link below to generate your token 👇")
    login_url = f"https://kite.trade/connect/login?api_key={st.secrets['Zerodha_API_Key']}"
    st.markdown(f"[🔗 Click here to login]({login_url})")
    st.info("📅 Timestamp updates on every token refresh.")

# Manual Refresh Button
if st.button("🔄 Refresh Now"):
    st.session_state["manual_refresh"] = True
else:
    st.session_state["manual_refresh"] = False

# Read credentials
creds_dict = json.loads(st.secrets["gspread_service_account"])
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Update LTPs manually if button pressed
if st.session_state["manual_refresh"]:
    try:
        update_ltp_sheet()
        st.success("✅ Live prices updated on Google Sheet.")
    except Exception as e:
        st.error(f"❌ Failed to update LTPs: {e}")

# Read LTPs from Google Sheet
ltp_data = pd.DataFrame(client.open("LiveLTPStore").sheet1.get_all_records())

# Read token from ZerodhaTokenStore
token_sheet = client.open("ZerodhaTokenStore").sheet1
tokens = token_sheet.get_all_values()[0]
api_key, api_secret, access_token = tokens[0], tokens[1], tokens[2]

# Save timestamp to D1
token_sheet.update("D1", [[str(datetime.now())]])

# Init Kite
kite = get_kite(api_key, access_token)

# Timeframes
TIMEFRAMES = {
    "15m": {"interval": "15minute", "days": 5},
    "1d": {"interval": "day", "days": 90},
}

# Analysis
symbols = ltp_data["Symbol"].tolist()
all_data = []

with st.spinner("🔍 Analyzing..."):
    for symbol in symbols:
        row = {"Symbol": symbol}
        try:
            ltp_row = ltp_data[ltp_data["Symbol"] == symbol]
            if not ltp_row.empty:
                row["LTP"] = float(ltp_row.iloc[0]["LTP"])
            for label, cfg in TIMEFRAMES.items():
                df = get_stock_data(kite, symbol, cfg["interval"], cfg["days"])
                if not df.empty:
                    scores = calculate_scores(df)
                    for key, val in scores.items():
                        adj_key = "TMV Score" if key == "Total Score" else key
                        row[f"{label} | {adj_key}"] = val
            all_data.append(row)
        except Exception as e:
            st.warning(f"⚠️ {symbol} failed: {e}")

# Build DataFrame
df = pd.DataFrame(all_data)
df["% Change"] = df["LTP"].pct_change().fillna(0).apply(lambda x: f"{x*100:.2f}%")

# Reorder columns
cols = df.columns.tolist()
cols.insert(1, cols.pop(cols.index("LTP")))
cols.insert(2, cols.pop(cols.index("% Change")))
df = df[cols]

# Highlight rules
highlight_green = (
    (df[["15m | Trend Direction", "1d | Trend Direction"]] == "Bullish").all(axis=1) &
    (df[["15m | TMV Score", "1d | TMV Score"]] >= 0.8).all(axis=1)
)
highlight_red = (
    (df[["15m | Trend Direction", "1d | Trend Direction"]] == "Bearish").all(axis=1) &
    (df[["15m | TMV Score", "1d | TMV Score"]] >= 0.8).all(axis=1)
)

def highlight(row):
    color = ""
    if highlight_green.loc[row.name]:
        color = "background-color: #d4edda; color: black"
    elif highlight_red.loc[row.name]:
        color = "background-color: #f8d7da; color: black"
    return [color] * len(row)

styled_df = df.style.apply(highlight, axis=1)

# Sort + Filter UI
sort_col = st.selectbox("Sort by", [col for col in df.columns if "Score" in col or "Reversal" in col])
sort_order = st.radio("Order", ["Descending", "Ascending"]) == "Ascending"
limit = st.slider("Top N Symbols", 1, len(df), 10)

df = df.sort_values(by=sort_col, ascending=sort_order).head(limit)

# Show
st.dataframe(df.style.apply(highlight, axis=1), use_container_width=True, hide_index=True)

# Download
excel = BytesIO()
df.to_excel(excel, index=False)
st.download_button("📥 Download Excel", excel.getvalue(), "stock_rankings.xlsx")

# Log to Sheet
try:
    log_to_google_sheets(sheet_name="Combined", df=df)
    st.success("✅ Data saved to Google Sheet.")
except Exception as e:
    st.warning(f"⚠️ Could not update Google Sheet: {e}")
