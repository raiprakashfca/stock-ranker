import streamlit as st
import pandas as pd
from kiteconnect import KiteConnect
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO

from utils.zerodha import get_stock_data
from utils.indicators import calculate_scores
from utils.sheet_logger import log_to_google_sheets

st.set_page_config(page_title="📊 Stock Ranker Dashboard", layout="wide", initial_sidebar_state="expanded")
st.title("📊 Multi-Timeframe Stock Ranking Dashboard")

# 🧱 Always-visible sidebar section
st.sidebar.title("⚙️ API Login & Configuration")
st.sidebar.markdown("➡️ Use the panel below to login to Zerodha or update expired tokens.")

# 🔐 Zerodha API Access Management
with st.sidebar.expander("🔐 Zerodha Access Token", expanded=True):
    st.markdown("This panel lets you manage Zerodha API tokens manually if needed.")

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = json.loads(st.secrets["gspread_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("ZerodhaTokenStore").sheet1
        tokens = sheet.get_all_values()[0]  # A1 = API Key, B1 = Secret, C1 = Access Token

        api_key = tokens[0]
        api_secret = tokens[1]
        access_token = tokens[2]

        st.markdown(f"[🔁 Click here to login to Zerodha](https://kite.zerodha.com/connect/login?v=3&api_key={api_key})")
        request_token = st.text_input("🔑 Paste new Request Token", key="manual_token")

        if request_token:
            try:
                kite = KiteConnect(api_key=api_key)
                session_data = kite.generate_session(request_token, api_secret=api_secret)
                sheet.update_cell(1, 3, session_data["access_token"])
                st.success("✅ Access token updated successfully. Please refresh the app.")
                st.stop()
            except Exception as e:
                st.error("❌ Failed to update token. Please try again.")
                st.exception(e)
    except Exception as e:
        st.error("❌ Failed to load Google Sheet or credentials.")
        st.exception(e)
        st.stop()

# ✅ API setup moved below the sidebar logic
kite = KiteConnect(api_key=tokens[0])
try:
    kite.set_access_token(tokens[2])
except Exception as e:
    st.error("⚠️ Access token invalid or expired. Use the sidebar to generate a new one.")
    st.stop()

# ⚙️ Configuration
TIMEFRAMES = {
    "15m": {"interval": "15minute", "days": 5},
    "1h": {"interval": "60minute", "days": 15},
    "1d": {"interval": "day", "days": 90},
}
SYMBOLS = ["RELIANCE", "TCS", "INFY", "ICICIBANK", "HDFCBANK", "SBIN", "BHARTIARTL"]

# 📊 Fetch & Analyze
all_data = []
with st.spinner("🔄 Fetching and scoring data..."):
    for symbol in SYMBOLS:
        row = {"Symbol": symbol}
        for label, config in TIMEFRAMES.items():
            df = get_stock_data(kite, symbol, config["interval"], config["days"])
            if df.empty:
                continue
            try:
                result = calculate_scores(df)
                for key, value in result.items():
                    row[f"{label} | {key}"] = value
            except Exception as e:
                st.warning(f"⚠️ Failed scoring {symbol} [{label}]: {e}")
        all_data.append(row)

# 🪄 Compile & Display
if all_data:
    df = pd.DataFrame(all_data)

    # Format column levels
    new_cols = []
    for col in df.columns:
        if col == "Symbol":
            new_cols.append(("Meta", "Symbol"))
        elif "|" in col:
            tf, metric = map(str.strip, col.split("|"))
            new_cols.append((tf, metric))
        else:
            new_cols.append(("Other", col))

    df.columns = pd.MultiIndex.from_tuples(new_cols)
    df = df.set_index(("Meta", "Symbol"))

    # Score to badge
    def format_badge(val):
        try:
            val = float(val)
            if val >= 0.75:
                return f"🟢 {val:.2f}"
            elif val >= 0.4:
                return f"🟡 {val:.2f}"
            else:
                return f"🔴 {val:.2f}"
        except:
            return val

    styled_df = df.style.format(format_badge)
    st.markdown("### 📈 Ranked Scores Across Timeframes")
    st.markdown("<div style='overflow-x:auto'>" + styled_df.to_html(escape=False) + "</div>", unsafe_allow_html=True)

    # 💾 Export
    excel_buffer = BytesIO()
    flat_df = df.reset_index()
    flat_df.columns = [' '.join(col).strip() if isinstance(col, tuple) else col for col in flat_df.columns]
    flat_df.to_excel(excel_buffer, index=False)
    st.download_button("📥 Download Excel", data=excel_buffer.getvalue(), file_name="stock_rankings.xlsx")

    # 📤 Sheet sync
    try:
        import streamlit as st  # Ensure st is defined here too
        log_to_google_sheets("Combined", flat_df)
        st.success("✅ Logged to Google Sheet")
    except Exception as e:
        st.warning(f"⚠️ Sheet log failed: {e}")

    # 📘 Legend
    st.markdown("""
    ### 🟢🟡🔴 Legend
    - **🟢 ≥ 0.75** = Strong
    - **🟡 0.4 - 0.75** = Moderate
    - **🔴 < 0.4** = Weak
    """)
else:
    st.error("❌ No data available for any symbol")
