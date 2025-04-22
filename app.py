
import os
import json
import pandas as pd
import streamlit as st
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from utils.zerodha import get_kite, get_stock_data, update_ltp_sheet
from utils.indicators import calculate_scores
from utils.sheet_logger import log_to_google_sheets
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="📊 Multi-Timeframe Stock Ranking Dashboard", layout="wide")
st_autorefresh(interval=5 * 60 * 1000, key="auto_refresh")

with st.sidebar:
    st.title("🔑 Zerodha API Login")
    try:
        login_url = f"https://kite.trade/connect/login?api_key={st.secrets['Zerodha_API_Key']}"
        st.markdown(f"[Click here to login to Zerodha]({login_url})", unsafe_allow_html=True)
        st.info("📅 Timestamp updates on every token refresh.")
    except KeyError:
        st.warning("⚠️ Missing Zerodha_API_Key in secrets.")

    if st.button("🔄 Refresh Now"):
        try:
            update_ltp_sheet()
            st.success("✅ LTPs refreshed successfully.")
        except Exception as e:
            st.error(f"❌ Failed to update LTPs: {e}")
        st.experimental_rerun()

try:
    creds_dict = st.secrets["gspread_service_account"]
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
except Exception as e:
    st.error("❌ Google Sheet authorization failed. Check your secrets.")
    st.stop()

try:
    sheet = client.open("BackgroundAnalysisStore").sheet1
    data = pd.DataFrame(sheet.get_all_records())
except Exception as e:
    st.error(f"❌ Could not load sheet data: {e}")
    st.stop()

if data.empty:
    st.warning("⚠️ Sheet is empty. Wait for background analysis.")
    st.stop()

# Move Symbol, LTP, % Change to front
cols = data.columns.tolist()
for col in ["Symbol", "LTP", "% Change"]:
    if col in cols:
        cols.insert(0, cols.pop(cols.index(col)))
data = data[cols]

# Sorting and filtering
sort_by = st.selectbox("📊 Sort by", [col for col in data.columns if "Score" in col or "Reversal" in col])
asc = st.radio("⬆️⬇️ Order", ["Descending", "Ascending"]) == "Ascending"
limit = st.slider("🔢 Top N symbols", 5, len(data), 10)
data = data.sort_values(by=sort_by, ascending=asc).head(limit)

# Highlighting
def highlight_row(row):
    trend = [row.get("15m Trend Direction"), row.get("1d Trend Direction")]
    score = [row.get("15m TMV Score", 0), row.get("1d TMV Score", 0)]
    if all(t == "Bullish" for t in trend) and all(s >= 0.8 for s in score):
        return ["background-color: #d4edda; color: black"] * len(row)
    elif all(t == "Bearish" for t in trend) and all(s >= 0.8 for s in score):
        return ["background-color: #f8d7da; color: black"] * len(row)
    else:
        return [""] * len(row)

st.dataframe(data.style.apply(highlight_row, axis=1), use_container_width=True)

# Excel export
from io import BytesIO
buffer = BytesIO()
data.to_excel(buffer, index=False)
st.download_button("📥 Download Excel", buffer.getvalue(), file_name="ranked_stocks.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# Log to Google Sheet (optional)
try:
    log_to_google_sheets("Combined", data)
except Exception as e:
    st.warning(f"⚠️ Logging failed: {e}")
