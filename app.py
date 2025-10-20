import os, json, logging
import numpy as np
import pandas as pd
import pytz
from datetime import datetime
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components
from kiteconnect import KiteConnect

# --- Our new one-click+paste token UI (single source of truth)
from utils.token_panel import render_token_panel
# If you still need these:
from fetch_ohlc import fetch_ohlc_data, calculate_indicators
from utils.token_utils import load_credentials_from_gsheet  # (keep only if you use API key/secret from sheet)

# ----------- Setup Logging -----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tmv_app")

# ----------- Streamlit Page Config -----------
st.set_page_config(page_title="📊 TMV Stock Ranking", layout="wide")

# ----------- 0) Token panel gate -----------
access_token = render_token_panel()
if not access_token:
    st.stop()  # no token -> no app

# ----------- 1) Load API key/secret (from your sheet util) -----------
# DO NOT cache the token read; a fresh paste should be visible immediately.
try:
    api_key, api_secret, _ = load_credentials_from_gsheet()
except Exception as e:
    st.sidebar.error(f"❌ Failed to load API Key/Secret from Google Sheet: {e}")
    st.stop()

# ----------- 2) Initialize Kite (verify token) -----------
try:
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    profile = kite.profile()  # lightweight sanity
    st.sidebar.success(f"🔐 Token OK: {profile['user_name']} ({profile['user_id']})")
except Exception as e:
    st.sidebar.markdown("### ❌ ZERODHA TOKEN INVALID")
    st.sidebar.error(f"Details: {e}")
    st.stop()

st.sidebar.markdown("---")
st.sidebar.info("🔄 Auto-refresh every 1 min. 🕒 Last Updated shown below.")

# ----------- 3) Auto-Refresh -----------
st_autorefresh(interval=60_000, key="refresh")
components.html(
    """
    <div style='font-size:14px;color:gray;'>
      Next refresh in <span id='cd'></span> seconds.
    </div>
    <script>
      let s=60; const e=document.getElementById('cd');
      (function u(){ e.innerText=s; if(s-->0) setTimeout(u,1000); })();
    </script>
    """,
    height=60
)

# ----------- 4) Title & Timestamp -----------
st.title("📈 Multi-Timeframe TMV Stock Ranking Dashboard")
now = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%d %b %Y, %I:%M %p IST")
st.markdown(f"#### 🕒 Last Updated: {now}")

# ----------- 5) Load your current ranked table from Sheet -----------
# NOTE: Keep this pointing to the sheet your pipeline populates (not a static demo).
csv_url = "https://docs.google.com/spreadsheets/d/1Cpgj1M_ofN1SqvuqDDHuN7Gy17tfkhy4fCCP8Mx7bRI/export?format=csv&gid=0"
try:
    df = pd.read_csv(csv_url)
    if df.empty or 'Symbol' not in df.columns:
        st.error("❌ LiveScores sheet is empty or invalid.")
        st.stop()
except Exception as e:
    st.error(f"❌ Error reading Google Sheet: {e}")
    st.stop()

# ----------- 6) Batch LTP fetch (simple & robust) -----------
def fetch_ltp_batch(symbols):
    """Fetch LTPs in chunks via kite.ltp(). Expects plain NSE symbols."""
    if not symbols:
        return {}
    keys = [f"NSE:{s.replace('_','-')}" for s in symbols]
    out = {}
    # kite.ltp can take many symbols at once, but chunk to be safe (e.g., 150 per call)
    CHUNK = 150
    for i in range(0, len(keys), CHUNK):
        chunk = keys[i:i+CHUNK]
        try:
            resp = kite.ltp(chunk)
            for k, v in resp.items():
                # k looks like "NSE:INFY"
                sym = k.split(":", 1)[1].replace('-', '_')
                out[sym] = v.get("last_price", np.nan)
        except Exception as e:
            logger.warning(f"LTP batch failed for {chunk[:3]}...: {e}")
    return out

symbols = df['Symbol'].dropna().astype(str).tolist()
ltp_map = fetch_ltp_batch(symbols)
df['LTP'] = df['Symbol'].map(lambda s: ltp_map.get(s, np.nan))

# Optional: % Change from your sheet might already exist; keep it if present
st.dataframe(df, use_container_width=True)

# ----------- 7) TMV Explainer (on-demand OHLC + indicators) -----------
st.markdown('---')
st.subheader('📘 TMV Explainer')

if not df.empty:
    sel = st.selectbox('Select a stock', df['Symbol'])
    if sel:
        sym_for_fetch = sel.replace('_','-')
        try:
            df15 = fetch_ohlc_data(sym_for_fetch, '15minute', 7)   # your util
            indicators = calculate_indicators(df15)                 # your util
            for name, val in indicators.items():
                st.markdown(f"**{name}:** {round(val,3) if isinstance(val,(int,float,float)) else val}")
        except Exception as e:
            st.error(f"Failed to compute indicators for {sel}: {e}")
