import streamlit as st
import pandas as pd
import pytz
import numpy as np
from datetime import datetime
from kiteconnect import KiteConnect, KiteTicker
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components

from fetch_ohlc import fetch_ohlc_data, calculate_indicators
from utils.token_utils import load_credentials_from_gsheet, save_token_to_gsheet

# ----------- Streamlit Page Config -----------
st.set_page_config(page_title="📊 TMV Stock Ranking", layout="wide")

# ----------- Load Zerodha Credentials (cached) -----------
# Cache credentials for 15 minutes to balance freshness and quota usage
@st.cache_data(ttl=900)
def get_creds():
    from gspread.exceptions import APIError
    try:
        return load_credentials_from_gsheet()
    except APIError as e:
        st.sidebar.error(f"❌ Failed to load credentials: {e}")
        st.stop()

api_key, api_secret, access_token = get_creds()

# ----------- Initialize Kite Client  -----------
kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# ----------- WebSocket Setup for LTP  -----------
instruments = kite.instruments(exchange="NSE")
instrument_map = {item["tradingsymbol"]: item["instrument_token"] for item in instruments}
ltp_ws = {}
kt = KiteTicker(api_key, access_token)

def on_ticks(ws, ticks):
    for t in ticks:
        sym = next((s for s, tok in instrument_map.items() if tok == t["instrument_token"]), None)
        if sym:
            ltp_ws[sym] = t["last_price"]

def on_connect(ws, response):
    tokens = list(instrument_map.values())
    kt.subscribe(tokens)
    kt.set_mode(tokens, kt.MODE_FULL)

kt.on_ticks = on_ticks
kt.on_connect = on_connect
kt.connect(threaded=True)

# ----------- Sidebar: Zerodha Token Generator -----------
with st.sidebar.expander("🔐 Zerodha Token Generator", expanded=False):
    kc = KiteConnect(api_key=api_key)
    login_url = kc.login_url()
    st.sidebar.write(login_url)  # Debug: exact login URL
    st.markdown(
        f'<a href="{login_url}" target="_blank">👉 Login to Zerodha</a>',
        unsafe_allow_html=True
    )
    request_token = st.text_input("Paste Request Token Here")
    if st.button("Generate Access Key"):
        try:
            session_data = kc.generate_session(request_token, api_secret=api_secret)
            new_token = session_data["access_token"]
            save_token_to_gsheet(new_token)
            kite.set_access_token(new_token)
            st.success("✅ Access Token saved successfully. Please refresh the page.")
            components.html('<script>window.location.reload();</script>', height=0)
        except Exception as e:
            st.error(f"❌ Failed to generate access token: {e}")

# ----------- Validate Token  -----------
try:
    profile = kite.profile()
    st.sidebar.success(f"🔐 Token verified: {profile['user_name']} ({profile['user_id']})")
except Exception as e:
    st.sidebar.error(f"❌ Token verification failed: {e}")
    st.stop()

st.sidebar.markdown("---")
st.sidebar.info("🔄 Auto-refresh every 1 min. 🕒 Last Updated shown below.")

# ----------- Auto-Refresh & Countdown -----------
st_autorefresh(interval=60000, key="refresh")
countdown_html = """
<div style='font-size:14px;color:gray;'>
Next refresh in <span id='cd'></span> seconds.
</div>
<script>
let s=60;
const e=document.getElementById('cd');
(function u(){ e.innerText = s; if(s-->0) setTimeout(u,1000); })();
</script>
"""
components.html(countdown_html, height=60)

# ----------- Title & Timestamp  -----------
st.title("📈 Multi-Timeframe TMV Stock Ranking Dashboard")
now = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%d %b %Y, %I:%M %p IST")
st.markdown(f"#### 🕒 Last Updated: {now}")

# ----------- Load & Display TMV Data with Live LTP  -----------
csv_url = (
    "https://docs.google.com/spreadsheets/d/"
    "1Cpgj1M_ofN1SqvuqDDHuN7Gy17tfkhy4fCCP8Mx7bRI/"
    "export?format=csv&gid=0"
)
df = pd.read_csv(csv_url)
if df.empty:
    st.warning("⚠️ Ranking sheet is empty.")
else:
    def get_live_ltp(sym):
        key = f"NSE:{sym.replace('_','-')}"
        return ltp_ws.get(sym) or kite.ltp([key])[key]["last_price"]
    df['LTP'] = df['Symbol'].map(get_live_ltp)
    st.dataframe(df)

# ----------- TMV Explainer  -----------
st.markdown('---')
st.subheader('📘 TMV Explainer')
if not df.empty:
    sel = st.selectbox('Select a stock', df['Symbol'])
    if sel:
        sym2 = sel.replace('_','-')
        df15 = fetch_ohlc_data(sym2, '15minute', 7)
        indicators = calculate_indicators(df15)
        for name, val in indicators.items():
            st.markdown(f"**{name}:** {round(val,3) if isinstance(val,(int,float)) else val}")
