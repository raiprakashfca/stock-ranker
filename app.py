import streamlit as st
import pandas as pd
from io import BytesIO
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="📊 Multi-Timeframe Stock Ranking Dashboard", layout="wide")

# Auto-refresh every 5 minutes (300000 ms)
st_autorefresh(interval=300000, key="auto_refresh")

# Google Sheet auth
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["gspread_service_account"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Load data from BackgroundAnalysisStore
sheet = client.open("BackgroundAnalysisStore").sheet1
data = sheet.get_all_records()
if not data:
    st.warning("No data available in BackgroundAnalysisStore sheet.")
    st.stop()

df = pd.DataFrame(data)

# Format numeric columns to 2 decimal places
for col in df.columns:
    if any(term in col for term in ["Score", "Reversal"]) or col == "% Change":
        df[col] = pd.to_numeric(df[col], errors="coerce").round(2)

# Sorting options
st.title("📊 Multi-Timeframe Stock Ranking Dashboard")
sort_col = st.selectbox("Sort by", df.columns[df.columns.str.contains("Score|Reversal|% Change")])
sort_asc = st.radio("Order", ["Descending", "Ascending"]) == "Ascending"
limit = st.slider("Top N Symbols", 1, len(df), min(20, len(df)))

df = df.sort_values(by=sort_col, ascending=sort_asc).head(limit)

# Styling based on rules
def style_row(row):
    cond_green = (
        row["15m Trend Direction"] == "Bullish" and
        row["1d Trend Direction"] == "Bullish" and
        row["15m TMV Score"] >= 0.8 and
        row["1d TMV Score"] >= 0.8
    )
    cond_red = (
        row["15m Trend Direction"] == "Bearish" and
        row["1d Trend Direction"] == "Bearish" and
        row["15m TMV Score"] >= 0.8 and
        row["1d TMV Score"] >= 0.8
    )
    color = "#d4edda" if cond_green else "#f8d7da" if cond_red else ""
    return ["background-color: {}".format(color)] * len(row)

styled_df = df.style.apply(style_row, axis=1)

st.dataframe(styled_df, use_container_width=True)

# Excel download
excel_buffer = BytesIO()
df.to_excel(excel_buffer, index=False)
st.download_button("📥 Download Excel", data=excel_buffer.getvalue(), file_name="stock_rankings.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
