
import json
import pandas as pd
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO

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

# Google Sheets credentials
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["gspread_service_account"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Read sheet
sheet = client.open("BackgroundAnalysisStore").sheet1
df = pd.DataFrame(sheet.get_all_records())

# Rearrange LTP and % Change to be next to Symbol
cols = df.columns.tolist()
symbol_idx = cols.index("Symbol")
ltp_idx = cols.index("LTP")
chg_idx = cols.index("% Change")
new_order = cols[:symbol_idx+1] + [cols[ltp_idx], cols[chg_idx]] + [c for i, c in enumerate(cols) if i not in (ltp_idx, chg_idx)]
df = df[new_order]

# Convert score fields to float and round
score_fields = [c for c in df.columns if "Score" in c or "Probability" in c]
for col in score_fields:
    df[col] = pd.to_numeric(df[col], errors="coerce").round(2)

# Filter/sort/limit
sort_column = st.selectbox("Sort by", df.columns.tolist(), index=df.columns.get_loc("1d TMV Score"))
sort_asc = st.radio("Order", ["Descending", "Ascending"]) == "Ascending"
limit = st.slider("Top N Symbols", 1, len(df), min(10, len(df)))
df = df.sort_values(by=sort_column, ascending=sort_asc).head(limit)

# Highlight rows based on direction + strength
def highlight_row(row):
    if row["15m Trend Direction"] == row["1d Trend Direction"] == "Bullish" and row["1d TMV Score"] >= 0.8:
        return ["background-color: #d4edda"] * len(row)
    elif row["15m Trend Direction"] == row["1d Trend Direction"] == "Bearish" and row["1d TMV Score"] >= 0.8:
        return ["background-color: #f8d7da"] * len(row)
    else:
        return [""] * len(row)

st.dataframe(df.style.apply(highlight_row, axis=1), use_container_width=True)

# Export to Excel
excel_buffer = BytesIO()
df.to_excel(excel_buffer, index=False)
st.download_button("📥 Download Excel", data=excel_buffer.getvalue(), file_name="stock_rankings.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
