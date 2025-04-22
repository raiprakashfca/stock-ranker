import json
import pandas as pd
import streamlit as st
from io import BytesIO
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# App configuration
st.set_page_config(page_title="📊 Multi-Timeframe Stock Ranking Dashboard", layout="wide")

# Sidebar toggle
if "sidebar_visible" not in st.session_state:
    st.session_state.sidebar_visible = True

def toggle_sidebar():
    st.session_state.sidebar_visible = not st.session_state.sidebar_visible

with st.sidebar:
    st.button("👁️ Toggle Sidebar", on_click=toggle_sidebar)
    if st.session_state.sidebar_visible:
        st.markdown("### Settings")
        st.markdown("Sidebar remains visible unless manually toggled.")

# Google Sheets Auth
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["gspread_service_account"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

sheet = client.open("BackgroundAnalysisStore").sheet1
data = sheet.get_all_records()
df = pd.DataFrame(data)

if df.empty:
    st.warning("🚨 No data available in BackgroundAnalysisStore.")
    st.stop()

# Ensure correct dtypes
df["LTP"] = pd.to_numeric(df["LTP"], errors="coerce")
df["% Change"] = df["% Change"].str.replace("%", "").astype(float)

# Sorting
sort_col = st.selectbox("Sort by", df.columns, index=3)
ascending = st.radio("Sort Order", ["Descending", "Ascending"]) == "Ascending"
top_n = st.slider("Top N Rows", 5, len(df), 20)

# Filter top rows
df = df.sort_values(by=sort_col, ascending=ascending).head(top_n)

# Highlight rules
def highlight(row):
    if (
        row["15m Trend Direction"] == "Bullish"
        and row["1d Trend Direction"] == "Bullish"
        and row["15m TMV Score"] >= 0.8
        and row["1d TMV Score"] >= 0.8
    ):
        return ["background-color: #d4edda"] * len(row)
    elif (
        row["15m Trend Direction"] == "Bearish"
        and row["1d Trend Direction"] == "Bearish"
        and row["15m TMV Score"] >= 0.8
        and row["1d TMV Score"] >= 0.8
    ):
        return ["background-color: #f8d7da"] * len(row)
    else:
        return [""] * len(row)

# Column order
columns = ["Symbol", "LTP", "% Change",
           "15m TMV Score", "15m Trend Direction", "15m Reversal Probability",
           "1d TMV Score", "1d Trend Direction", "1d Reversal Probability"]
df = df[columns]

# Apply highlighting
styled = df.style.apply(highlight, axis=1).format("{:.2f}", subset=["LTP", "% Change", "15m TMV Score", "1d TMV Score", "15m Reversal Probability", "1d Reversal Probability"])

# Display
st.markdown("### 📈 Stock Scores (Live View from Background Sheet)")
st.dataframe(styled, use_container_width=True)

# Export
buffer = BytesIO()
df.to_excel(buffer, index=False)
st.download_button("📥 Download Excel", buffer.getvalue(), "stock_ranking.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
