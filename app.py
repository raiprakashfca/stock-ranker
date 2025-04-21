import json
import pandas as pd
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO

# Set page config
st.set_page_config(page_title="📊 Fast Stock Rankings", layout="wide")

# Custom CSS
st.markdown("""
<style>
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

st.title("🚀 Fast Stock Rankings (Powered by Background Engine)")

# Auto-refresh every 5 minutes
st.experimental_rerun = st.query_params.get("refresh", False)
st.experimental_set_query_params(refresh=True)

# Google Sheets auth
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["gspread_service_account"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Read from BackgroundAnalysisStore
sheet = client.open("BackgroundAnalysisStore").sheet1
data = pd.DataFrame(sheet.get_all_records())

if data.empty:
    st.warning("⚠️ No data available in BackgroundAnalysisStore.")
    st.stop()

# Format % Change
data["% Change"] = data["% Change"].apply(lambda x: f"{float(x):+.2f}%" if isinstance(x, (float, int)) else x)

# Render badges
def render_score(score):
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

def render_direction(direction):
    if direction == "Bullish":
        return "<span class='direction bullish'>🟢 Bullish</span>"
    elif direction == "Bearish":
        return "<span class='direction bearish'>🔴 Bearish</span>"
    elif direction == "Neutral":
        return "<span class='direction neutral'>🟡 Neutral</span>"
    else:
        return direction

def render_reversal(prob):
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

# Format selected columns
format_dict = {}
for col in data.columns:
    if "Score" in col:
        format_dict[col] = render_score
    elif "Direction" in col:
        format_dict[col] = render_direction
    elif "Reversal" in col:
        format_dict[col] = render_reversal

styled_df = data.style.format(format_dict, escape="html")

# Display
st.markdown("### 📈 Latest Ranked Data (from background engine)")
st.markdown('<div style="overflow-x:auto;">' + styled_df.to_html(escape=False) + '</div>', unsafe_allow_html=True)

# Export
excel_buffer = BytesIO()
data.to_excel(excel_buffer, index=False)
st.download_button("📥 Download Excel", data=excel_buffer.getvalue(), file_name="fast_stock_rankings.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
