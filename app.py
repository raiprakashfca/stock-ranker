import streamlit as st
import pandas as pd
import pytz
import numpy as np
from datetime import datetime, timedelta
from kiteconnect import KiteConnect, KiteTicker
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components
import pandas_ta as ta

from fetch_ohlc import fetch_ohlc_data, calculate_indicators
from utils.token_utils import load_credentials_from_gsheet, save_token_to_gsheet

# ----------- Streamlit Page Config -----------
st.set_page_config(page_title="📊 TMV Stock Ranking", layout="wide")

# ----------- Load Zerodha Credentials -----------
# Cache credentials to avoid exceeding GSheet read quota
@st.cache_data(ttl=86400)  # Cache credentials once per day since they change infrequently
def get_creds():
    from gspread.exceptions import APIError
    try:
        return load_credentials_from_gsheet()
    except APIError as e:
        st.sidebar.error(f"❌ Failed to load credentials from Google Sheet: {e}")
        st.stop()

api_key, api_secret, access_token = get_creds()

# ----------- Initialize Kite Client & WebSocket -----------
kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# Prepare instrument-token map for WebSocket
instruments = kite.instruments(exchange="NSE")
instrument_map = {item["tradingsymbol"]: item["instrument_token"] for item in instruments}

ltp_ws = {}
kt = KiteTicker(api_key, access_token)

def on_ticks(ws, ticks):
    for t in ticks:
        # Reverse map: match instrument_token to tradingsymbol
        sym = next((s for s, tok in instrument_map.items() if tok == t['instrument_token']), None)
        if sym:
            ltp_ws[sym] = t['last_price']

def on_connect(ws, response):
    # Subscribe to all tokens in universe dynamically later
    pass

kt.on_ticks = on_ticks
kt.on_connect = on_connect
kt.connect(threaded=True)

# ----------- Sidebar: Token Generator -----------
with st.sidebar.expander("🔐 Zerodha Token Generator", expanded=False):
    # Generate login URL using KiteConnect's built-in method
    kc = KiteConnect(api_key=api_key)
    login_url = kc.login_url()
    # Display raw login URL for debugging
    st.sidebar.write(login_url)
    # Display clickable link that opens in a new tab
    st.markdown(
        f"<a href=\"{login_url}\" target=\"_blank\" rel=\"noopener noreferrer\">👉 Login to Zerodha</a>",
        unsafe_allow_html=True
    )
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
st.sidebar.info("🔄 Data auto-refreshes every 1 minute.\n🕒 Last updated time shown on dashboard.")

# ----------- Auto-Refresh -----------
st_autorefresh(interval=60000, key="refresh")

# ----------- Countdown UI -----------
countdown_html = """
<div style='font-size:14px;color:gray;'>
Next refresh in <span id='countdown'></span> seconds.
</div>
<script>
var seconds=60;const el=document.getElementById('countdown');
function upd(){el.innerText=seconds; if(seconds-->0) setTimeout(upd,1000);} upd();
</script>
"""
components.html(countdown_html, height=70)

# ----------- Title & Timestamp -----------
st.title("📈 Multi-Timeframe TMV Stock Ranking Dashboard")
now = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%d %b %Y, %I:%M %p IST")
st.markdown(f"#### 🕒 Last Updated: {now}")

# ----------- Load & Normalize Ranking Data -----------
csv_url = (
    "https://docs.google.com/spreadsheets/d/"
    "1Cpgj1M_ofN1SqvuqDDHuN7Gy17tfkhy4fCCP8Mx7bRI/"
    "export?format=csv&gid=0"
)
df = pd.read_csv(csv_url)
if df.empty:
    st.warning("⚠️ Ranking sheet is empty.")
else:
    # Z-score normalization of TMV Score columns
    score_cols = [c for c in df.columns if 'TMV Score' in c]
    for col in score_cols:
        mean, std = df[col].mean(), df[col].std()
        df[col + ' Z'] = df[col].apply(lambda x: (x - mean) / std if std else 0)
    # Fetch live LTPs from WebSocket or fallback to REST
    df['LTP'] = df['Symbol'].map(lambda s: ltp_ws.get(s) or kite.ltp([f"NSE:{s.replace('_','-')}"])[f"NSE:{s.replace('_','-')}"]['last_price'])
    # VWAP deviation: compute VWAP intraday
    def get_vwap(sym):
        try:
            data = fetch_ohlc_data(sym.replace('_','-'), 'minute', 1)
            if data is None or data.empty:
                return None
            vwap_series = ta.vwap(data['high'], data['low'], data['close'], data['volume'])
            return vwap_series.iloc[-1] if not vwap_series.empty else None
        except Exception as e:
            st.error(f"❌ Error computing VWAP for {sym}: {e}")
            return None

    # Calculate VWAP for each symbol with error handling
    vwap_values = []
    for sym in df['Symbol']:
        vwap_values.append(get_vwap(sym))
    df['VWAP'] = vwap_values
    df['VWAP Dev %'] = df.apply(lambda row: ((row['LTP'] - row['VWAP']) / row['VWAP'] * 100).round(2)
                                 if row['VWAP'] not in (None, 0) else None, axis=1)
    
    # Reorder
    cols = ['Symbol', 'LTP', 'VWAP', 'VWAP Dev %'] + [c for c in df.columns if c not in ['Symbol','LTP','VWAP','VWAP Dev %']]
    df = df[cols]
    fmt = {c: '{:.2f}' for c in df.columns if any(k in c for k in ['Score','Z','LTP','VWAP','Dev'])}
    st.dataframe(df.style.format(fmt))
# Reorder
    cols = ['Symbol', 'LTP', 'VWAP', 'VWAP Dev %'] + [c for c in df.columns if c not in ['Symbol','LTP','VWAP','VWAP Dev %']]
    df = df[cols]
    fmt = {c: '{:.2f}' for c in df.columns if any(k in c for k in ['Score','Z','LTP','VWAP','Dev'])}
    st.dataframe(df.style.format(fmt))

# ----------- TMV Explainer with Advanced Contextual Modeling -----------
st.markdown('---')
st.subheader('📘 TMV Explainer')
if not df.empty:
    sel = st.selectbox('Select a stock to explain', df['Symbol'].unique())
    if sel:
        sym = sel.replace('_','-')
        df_15 = fetch_ohlc_data(sym, '15minute', 7)
        df_1d = fetch_ohlc_data(sym, 'day', 90)
        ind15 = calculate_indicators(df_15)
        ind1d = calculate_indicators(df_1d)
        # Additional indicators
        adx = ta.adx(df_15['high'],df_15['low'],df_15['close']).iloc[-1]['ADX_14']
        st_adv = ta.supertrend(df_15['high'],df_15['low'],df_15['close']).iloc[-1]['SUPERT_7_3.0']
        obv = ta.obv(df_15['close'],df_15['volume']).iloc[-1]
        # Regression slope
        slope = np.polyfit(np.arange(len(df_15)), df_15['close'], 1)[0]
        # Percentile ranks for RSI
        rsi_series = pd.Series(df_15['RSI']) if 'RSI' in df_15 else ta.rsi(df_15['close']).iloc
        pctile = rsi_series.rank(pct=True).iloc[-1]
        # Display
        st.markdown(f"**15m ADX:** {adx:.2f} | **SuperTrend:** {st_adv:.2f} | **OBV:** {obv:.0f}")
        st.markdown(f"**Price Slope:** {slope:.4f} | **RSI Percentile:** {pctile*100:.1f}%")
        with st.expander('🔍 Full 15m Indicators'):
            for k,v in ind15.items(): st.markdown(f"**{k}:** {v}")
        with st.expander('🔍 Full 1d Indicators'):
            for k,v in ind1d.items(): st.markdown(f"**{k}:** {v}")
