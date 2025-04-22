
import json
import pandas as pd
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO
from streamlit_autorefresh import st_autorefresh

# Auto-refresh every 5 minutes (300000 ms)
st_autorefresh(interval=300000, key="autorefresh")

st.set_page_config(page_title="📊 Multi-Timeframe Stock Ranking Dashboard", layout="wide")

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

# Load GSheet creds
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["gspread_service_account"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

sheet = client.open("BackgroundAnalysisStore").sheet1
df = pd.DataFrame(sheet.get_all_records())

if df.empty:
    st.warning("⚠️ No data available in BackgroundAnalysisStore.")
    st.stop()

# Ensure numeric formatting
for col in df.columns:
    if 'Score' in col or 'Reversal Probability' in col:
        df[col] = pd.to_numeric(df[col], errors='coerce').round(2)

# Reorder columns
first_cols = ['Symbol', 'LTP', '% Change']
score_cols = [col for col in df.columns if col not in first_cols]
df = df[first_cols + score_cols]

# Highlight logic
highlight_conditions = (
    (df[["15m Trend Direction", "1d Trend Direction"]] == "Bullish").all(axis=1) &
    (df[["15m TMV Score", "1d TMV Score"]] >= 0.8).all(axis=1)
)
highlight_red = (
    (df[["15m Trend Direction", "1d Trend Direction"]] == "Bearish").all(axis=1) &
    (df[["15m TMV Score", "1d TMV Score"]] >= 0.8).all(axis=1)
)

def highlight_row(row):
    if highlight_conditions.loc[row.name]:
        return ["background-color: #d4edda"] * len(row)
    elif highlight_red.loc[row.name]:
        return ["background-color: #f8d7da"] * len(row)
    else:
        return [""] * len(row)

styled_df = df.style.apply(highlight_row, axis=1)
st.dataframe(styled_df, use_container_width=True, hide_index=False)

# Export to Excel
excel_buffer = BytesIO()
df.to_excel(excel_buffer, index=False)
st.download_button("📥 Download Excel", data=excel_buffer.getvalue(), file_name="stock_rankings.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
