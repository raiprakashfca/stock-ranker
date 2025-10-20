import os, json, logging
import numpy as np
import pandas as pd
import pytz
from datetime import datetime, timedelta, time
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components
from kiteconnect import KiteConnect

# --- One-click+paste token UI (single source of truth)
from utils.token_panel import render_token_panel
# Your existing utils:
from fetch_ohlc import fetch_ohlc_data, calculate_indicators
from utils.token_utils import load_credentials_from_gsheet  # reads API key/secret from Sheet

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
now = datetime.now(pytz.timezone('Asia/Kolkata'))
st.markdown(f"#### 🕒 Last Updated: {now.strftime('%d %b %Y, %I:%M %p IST')}")

# ----------- 4.1 LIVE banner + watermarks -----------
st.markdown(
    f"> **MODE:** LIVE (KiteConnect) &nbsp;|&nbsp; **Computed-At (IST):** {now.isoformat(timespec='seconds')} &nbsp;|&nbsp; **Source:** kite.ltp()",
    help="If this ever shows BACKTEST, the app should not display live scores."
)

# ----------- 5) Load your current ranked table from Sheet -----------
# Make the CSV URL configurable (no hard-coding in code). Fallback to your current URL if env not set.
CSV_URL = os.getenv(
    "LIVE_SCORES_CSV_URL",
    "https://docs.google.com/spreadsheets/d/1Cpgj1M_ofN1SqvuqDDHuN7Gy17tfkhy4fCCP8Mx7bRI/export?format=csv&gid=0"
)
try:
    df = pd.read_csv(CSV_URL)
    if df.empty or 'Symbol' not in df.columns:
        st.error("❌ LiveScores sheet is empty or invalid (no 'Symbol' column).")
        st.stop()
    # Standardize Symbol dtype early
    df['Symbol'] = df['Symbol'].astype(str)
except Exception as e:
    st.error(f"❌ Error reading Google Sheet: {e}")
    st.stop()

# ----------- 6) Freshness gate (15m candles) -----------
# Quick probe on one symbol to ensure latest 15m candle isn't stale (>20 min during market hours).
def in_market_hours(ts_ist: datetime) -> bool:
    return ts_ist.weekday() < 5 and time(9, 15) <= ts_ist.time() <= time(15, 30)

if not df.empty:
    try:
        probe = df['Symbol'].iloc[0].replace('_', '-')
        df15 = fetch_ohlc_data(probe, '15minute', 1)  # your util should return a DataFrame with 'date'
        if isinstance(df15, pd.DataFrame) and not df15.empty and 'date' in df15.columns:
            last_dt = df15['date'].iloc[-1]
            # Ensure tz-aware IST
            if pd.api.types.is_datetime64_any_dtype(df15['date']):
                if last_dt.tzinfo is None:
                    # assume IST if naive
                    last_dt = last_dt.tz_localize('Asia/Kolkata')
            freshness = (now - last_dt).total_seconds() / 60.0
            if in_market_hours(now) and freshness > 20:
                st.error(f"🛑 Data stale: latest 15m candle ends at {last_dt} (age ≈ {freshness:.0f} min). "
                         f"Not rendering scores to avoid bad decisions.")
                st.stop()
        else:
            st.warning("Could not verify freshness (missing 15m candles). Proceed with caution.")
    except Exception as e:
        st.warning(f"Freshness check skipped due to error: {e}")

# ----------- 7) Batch LTP fetch (simple & robust) -----------
def fetch_ltp_batch(symbols):
    """Fetch LTPs in chunks via kite.ltp(). Expects plain NSE symbols (with underscores)."""
    if not symbols:
        return {}
    keys = [f"NSE:{s.replace('_','-')}" for s in symbols]
    out = {}
    CHUNK = 150
    for i in range(0, len(keys), CHUNK):
        chunk = keys[i:i+CHUNK]
        try:
            resp = kite.ltp(chunk)
            for k, v in resp.items():
                sym = k.split(":", 1)[1].replace('-', '_')
                out[sym] = v.get("last_price", np.nan)
        except Exception as e:
            logger.warning(f"LTP batch failed for {chunk[:3]}...: {e}")
    return out

symbols = df['Symbol'].dropna().tolist()
ltp_map = fetch_ltp_batch(symbols)
df['LTP'] = df['Symbol'].map(lambda s: ltp_map.get(s, np.nan))

st.dataframe(df, use_container_width=True)

# ----------- 8) TMV Explainer (on-demand OHLC + indicators) -----------
st.markdown('---')
st.subheader('📘 TMV Explainer')

if not df.empty:
    sel = st.selectbox('Select a stock', df['Symbol'])
    if sel:
        sym_for_fetch = sel.replace('_', '-')
        try:
            df15 = fetch_ohlc_data(sym_for_fetch, '15minute', 7)   # your util
            indicators = calculate_indicators(df15)                 # your util
            for name, val in indicators.items():
                st.markdown(f"**{name}:** {round(val,3) if isinstance(val,(int,float)) else val}")
        except Exception as e:
            st.error(f"Failed to compute indicators for {sel}: {e}")
