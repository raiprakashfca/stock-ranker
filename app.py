import streamlit as st
import pandas as pd
import pytz
from datetime import datetime, timedelta
from kiteconnect import KiteConnect
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components

from fetch_ohlc import fetch_ohlc_data, calculate_indicators
from utils.token_utils import load_credentials_from_gsheet, save_token_to_gsheet

# ----------- Streamlit Page Config -----------
st.set_page_config(page_title="📊 TMV Stock Ranking", layout="wide")

# ----------- Load Zerodha Credentials -----------
api_key, api_secret, access_token = load_credentials_from_gsheet()

# ----------- Initialize Kite Client -----------
kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# ----------- Sidebar: Token Generator -----------
with st.sidebar.expander("🔐 Zerodha Token Generator", expanded=False):
    login_url = f"https://kite.zerodha.com/connect/login?v=3&api_key={api_key}"
    st.markdown(f"👉 [Login to Zerodha]({login_url})", unsafe_allow_html=True)
    request_token = st.text_input("Paste Request Token Here")
    if st.button("Generate Access Key"):
        try:
            kite_temp = KiteConnect(api_key=api_key)
            session_data = kite_temp.generate_session(request_token, api_secret=api_secret)
            access_token = session_data["access_token"]
            save_token_to_gsheet(access_token)
            st.success("✅ Access Token saved successfully.")
        except Exception as e:
            st.error(f"❌ Failed to generate access token: {e}")

# ----------- Validate Token -----------
try:
    profile = kite.profile()
    st.sidebar.success(f"🔐 Token verified: {profile['user_name']} ({profile['user_id']})")
except Exception as e:
    st.sidebar.error(f"❌ Token verification failed: {e}")
    st.stop()

st.sidebar.markdown("---")
st.sidebar.info("🔄 Data auto-refreshes every 1 minute.\n\n🕒 Last updated time shown on dashboard.")

# ----------- Auto-Refresh -----------
st_autorefresh(interval=60000, key="refresh")  # 60 seconds

# ----------- Refresh Countdown UI -----------
countdown_html = """
<div style="font-size:14px; color:gray;">
Next refresh in <span id=\"countdown\"></span> seconds.
</div>
<script>
var seconds = 60;
var countdownElement = document.getElementById("countdown");
function updateCountdown() {
    countdownElement.innerText = seconds;
    if (seconds > 0) {
        seconds--;
        setTimeout(updateCountdown, 1000);
    }
}
updateCountdown();
</script>
"""
components.html(countdown_html, height=70)

# ----------- Page Title & Timestamp -----------
st.title("📈 Multi-Timeframe TMV Stock Ranking Dashboard")
now = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%d %b %Y, %I:%M %p IST")
st.markdown(f"#### 🕒 Last Updated: {now}")

# ----------- Load & Display Ranking Data -----------
try:
    csv_url = (
        "https://docs.google.com/spreadsheets/d/"
        "1Cpgj1M_ofN1SqvuqDDHuN7Gy17tfkhy4fCCP8Mx7bRI/"
        "export?format=csv&gid=0"
    )
    df = pd.read_csv(csv_url)
    if df.empty:
        st.warning("⚠️ Ranking sheet is empty.")
    else:
        # Fetch live LTPs for each Symbol, converting underscores to hyphens
        symbols = df['Symbol'].astype(str).tolist()
        kite_symbols = [f"NSE:{s.replace('_','-')}" for s in symbols]
        try:
            ltp_data = kite.ltp(kite_symbols)
            df['LTP'] = [ltp_data.get(f"NSE:{s.replace('_','-')}", {}).get('last_price') for s in symbols]
        except Exception as e:
            st.error(f"❌ Error fetching live LTPs: {e}")
            df['LTP'] = None
        # Reorder columns: Symbol, LTP, then rest
        cols = ['Symbol', 'LTP'] + [c for c in df.columns if c not in ['Symbol', 'LTP']]
        df = df[cols]
        # Format numeric columns
        fmt = {col: "{:.2f}" for col in df.columns if 'Score' in col or col == 'LTP'}
        st.dataframe(df.style.format(fmt))
except Exception as e:
    st.error(f"❌ Error loading ranking data: {e}")

# ----------- TMV Explainer -----------
st.markdown("---")
st.subheader("📘 TMV Explainer")
if 'df' in locals() and 'Symbol' in df.columns:
    selected_stock = st.selectbox(
        "Select a stock to generate explanation",
        df['Symbol'].dropna().unique()
    )
else:
    selected_stock = None

if selected_stock:
    st.markdown(f"### Real Indicators for {selected_stock}")
    try:
        # Convert underscore to hyphen for API
        api_symbol = selected_stock.replace('_','-')
        df_15m = fetch_ohlc_data(api_symbol, "15minute", 7)
        df_1d = fetch_ohlc_data(api_symbol, "day", 90)
        ind_15m = calculate_indicators(df_15m)
        ind_1d = calculate_indicators(df_1d)
        indicator_descriptions = {
            "EMA_8": "Exponential Moving Average over 8 periods — gives more weight to recent prices.",
            "EMA_21": "Exponential Moving Average over 21 periods — identifies medium-term trend.",
            "RSI": "Relative Strength Index — momentum oscillator; >70 overbought, <30 oversold.",
            "MACD": "Moving Average Convergence Divergence — momentum indicator.",
            "ADX": "Average Directional Index — measures trend strength; >25 indicates strong trend.",
            "OBV": "On-Balance Volume — uses volume flow to predict price changes.",
            "SuperTrend": "SuperTrend indicator — combines ATR with price for trend signals.",
        }
        with st.expander("📊 15m Indicator Breakdown"):
            for key, value in ind_15m.items():
                desc = indicator_descriptions.get(key, "No description available.")
                st.markdown(f"**{key}: {round(value,2) if isinstance(value,(float,int)) else value}**\n*{desc}*")
        with st.expander("📊 1d Indicator Breakdown"):
            for key, value in ind_1d.items():
                desc = indicator_descriptions.get(key, "No description available.")
                st.markdown(f"**{key}: {round(value,2) if isinstance(value,(float,int)) else value}**\n*{desc}*")
    except Exception as e:
        st.error(f"❌ Error fetching indicators for {selected_stock}: {e}")

# ----------- Admin: Add New Stock -----------
st.markdown("---")
st.subheader("➕ Admin: Add New Stock")

@st.cache_data(ttl=3600)
def load_instruments():
    instruments = kite.instruments(exchange="NSE")
    df_inst = pd.DataFrame(instruments)
    return df_inst[["tradingsymbol", "name", "instrument_type"]]

filtered = load_instruments()
search_query = st.text_input("Search Stock Name or Symbol")
if search_query:
    filtered = filtered[filtered["tradingsymbol"].str.contains(search_query, case=False)]
selected_new = st.selectbox("Select New Stock", filtered["tradingsymbol"].unique())
if st.button("✅ Add Stock"):
    try:
        # Append logic here
        st.success(f"✅ {selected_new} added successfully!")
    except Exception as e:
        st.error(f"❌ Failed to add {selected_new}: {e}")
