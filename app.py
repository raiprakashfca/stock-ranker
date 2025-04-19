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
    .score-badge {
        display: inline-block;
        padding: 6px 12px;
        border-radius: 12px;
        font-weight: 600;
        color: white;
    }
    .high { background-color: #28a745; }
    .medium { background-color: #ffc107; color: black; }
    .low { background-color: #dc3545; }
    .section-card {
        background-color: #f9f9f9;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    </style>
""", unsafe_allow_html=True)

st.title("📊 Multi-Timeframe Stock Ranking Dashboard")

# Login Section
with st.sidebar:
    st.header("🔐 Zerodha Login")
    api_key_input = st.text_input("API Key")
    api_secret_input = st.text_input("API Secret", type="password")
    request_token_input = st.text_input("Request Token")

    kite = None
    if api_key_input and api_secret_input:
        kite = KiteConnect(api_key=api_key_input)
        login_url = kite.login_url()
        st.markdown(f"[🔑 Generate Request Token]({login_url})")

        if request_token_input:
            try:
                data = kite.generate_session(request_token_input, api_secret=api_secret_input)
                access_token = data["access_token"]
                kite.set_access_token(access_token)

                scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                creds_dict = json.loads(st.secrets["gspread_service_account"])
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
                client = gspread.authorize(creds)
                sheet = client.open("ZerodhaTokenStore")
                sheet.sheet1.update("A1", [[api_key_input, api_secret_input, access_token]])
                st.success("✅ Access token saved.")
            except Exception as e:
                st.error(f"❌ Token generation failed: {e}")
                st.stop()
    else:
        st.info("ℹ️ Enter credentials to begin")
        st.stop()

if not kite:
    st.stop()

# Timeframe Configs
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
                    for k, v in result.items():
                        row[f"{k} ({label})"] = v
                except Exception as e:
                    st.warning(f"⚠️ {symbol} ({label}) failed: {e}")
        all_data.append(row)

if not all_data:
    st.error("❌ No stock data available.")
    st.stop()

final_df = pd.DataFrame(all_data)

# Sort and Filter Section
st.markdown("### 🔎 Filter and Sort")
sort_column = st.selectbox("Sort by", [col for col in final_df.columns if "Total Score" in col])
sort_asc = st.radio("Order", ["Descending", "Ascending"]) == "Ascending"
limit = st.slider("Top N Symbols", 1, len(final_df), 10)

# Score badge function
def render_badge(score):
    if score >= 0.75:
        return f"<span class='score-badge high'>{score:.2f}</span>"
    elif score >= 0.4:
        return f"<span class='score-badge medium'>{score:.2f}</span>"
    else:
        return f"<span class='score-badge low'>{score:.2f}</span>"

# Display Sorted and Filtered
display_df = final_df[[col for col in final_df.columns if "Total Score" in col or "Symbol" in col]].copy()
display_df = display_df.sort_values(by=sort_column, ascending=sort_asc).head(limit).set_index("Symbol")

styled = display_df.style.format("{:.2f}")
for col in display_df.columns:
    styled = styled.format({col: lambda x: render_badge(x)}, escape="html")

st.markdown("<div class='section-card'>", unsafe_allow_html=True)
st.markdown("### 📈 Top-Level Scores")
st.write(styled.to_html(escape=False), unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

# Expandable Raw Indicator Panel
with st.expander("🧪 View Raw Indicator Values per Timeframe"):
    for symbol in symbols:
        st.markdown(f"#### {symbol}")
        for label in TIMEFRAMES:
            indicator_cols = [
                f"EMA8 ({label})", f"EMA21 ({label})", f"MACD ({label})", f"RSI ({label})", f"ADX ({label})",
                f"OBV ({label})", f"MFI ({label})", f"SUPERT ({label})", f"HULL ({label})", f"ALLIGATOR ({label})", f"FAMA ({label})"
            ]
            subset = final_df[final_df.Symbol == symbol][indicator_cols].transpose().reset_index()
            subset.columns = ["Indicator", f"Value ({label})"]
            st.dataframe(subset, use_container_width=True)

# Export Excel button
excel_buffer = BytesIO()
final_df.to_excel(excel_buffer, index=False)
st.download_button("📥 Download Excel", data=excel_buffer.getvalue(), file_name="stock_rankings.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

try:
    log_to_google_sheets(sheet_name="Combined", df=final_df)
    st.success("✅ Data saved to Google Sheet.")
except Exception as e:
    st.warning(f"⚠️ Sheet log failed: {e}")
