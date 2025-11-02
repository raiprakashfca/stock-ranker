import os, json, logging
import numpy as np
import pandas as pd
import pytz
from datetime import datetime
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components
from kiteconnect import KiteConnect

from utils.token_panel import render_token_panel
from utils.token_utils import load_credentials_from_gsheet

# -----------------------------
# Make Streamlit secrets visible to modules that read env vars
# (token_panel expects env keys)
# -----------------------------
if "ZERODHA_TOKEN_SHEET_KEY" in st.secrets:
    os.environ["ZERODHA_TOKEN_SHEET_KEY"] = st.secrets["ZERODHA_TOKEN_SHEET_KEY"]
if "GOOGLE_SERVICE_ACCOUNT_JSON" in st.secrets:
    os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"] = st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"]
if "LIVE_SCORES_CSV_URL" in st.secrets:
    os.environ["LIVE_SCORES_CSV_URL"] = st.secrets["LIVE_SCORES_CSV_URL"]

# -----------------------------
# Page & logging
# -----------------------------
st.set_page_config(page_title="📊 TMV Stock Ranking", layout="wide")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tmv_app")

# -----------------------------
# Use existing token from Google Sheet if possible
# -----------------------------
api_key, api_secret, access_token = load_credentials_from_gsheet()
kite = KiteConnect(api_key=api_key)
expiry_time = None

try:
    # Try stored token
    kite.set_access_token(access_token)
    profile = kite.profile()

    # Read token expiry info (D1) from ZerodhaTokenStore (nice-to-have)
    import gspread
    from google.oauth2.service_account import Credentials
    sa_json = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(
        sa_json,
        scopes=["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    )
    gc = gspread.authorize(creds)
    ws_token = gc.open("ZerodhaTokenStore").worksheet("Sheet1")
    expiry_time = ws_token.acell("D1").value

    st.sidebar.success(f"🔐 Token OK: {profile['user_name']} ({profile['user_id']})")
    if expiry_time:
        st.sidebar.info(f"⏳ Token valid until: {expiry_time}")

except Exception as e:
    # Fallback to login+paste panel
    st.sidebar.warning("⚠️ Stored token invalid or expired. Please log in again.")
    access_token = render_token_panel()
    if not access_token:
        st.stop()

    kite.set_access_token(access_token)
    profile = kite.profile()
    st.sidebar.success(f"🔐 Token refreshed for {profile['user_name']} ({profile['user_id']})")

# -----------------------------
# Sidebar: auto-refresh
# -----------------------------
st.sidebar.markdown("---")
st.sidebar.info("🔄 Auto-refresh every 1 min. 🕒 Last Updated shown below.")
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

# -----------------------------
# Title & timestamp
# -----------------------------
st.title("📈 Multi-Timeframe TMV Stock Ranking Dashboard")
now = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%d %b %Y, %I:%M %p IST")
st.markdown(f"#### 🕒 Last Updated: {now}")

# -----------------------------
# Load TMV Scores CSV
# -----------------------------
csv_url = os.getenv(
    "LIVE_SCORES_CSV_URL",
    "https://docs.google.com/spreadsheets/d/1Cpgj1M_ofN1SqvuqDDHuN7Gy17tfkhy4fCCP8Mx7bRI/export?format=csv&gid=0"
)
try:
    df = pd.read_csv(csv_url)
    if df.empty or "Symbol" not in df.columns:
        st.error("❌ LiveScores sheet is empty or invalid.")
        st.stop()
except Exception as e:
    st.error(f"❌ Error reading Google Sheet: {e}")
    st.stop()

# -----------------------------
# Freshness utilities
# -----------------------------
IST = pytz.timezone("Asia/Kolkata")

def looks_stale(df_in: pd.DataFrame) -> bool:
    """
    Heuristics:
      1) If a timestamp column exists (LastUpdated/UpdatedAt/RunDate), ensure it's today IST.
      2) If no timestamp column, check if all LTP are NaN/0 after LTP fill.
    """
    for col in ["LastUpdated", "UpdatedAt", "RunDate"]:
        if col in df_in.columns:
            try:
                ts = pd.to_datetime(df_in[col].iloc[0], errors="coerce")
                if pd.isna(ts):
                    continue
                # localize if naive
                if ts.tzinfo is None:
                    ts = IST.localize(ts)
                return ts.astimezone(IST).date() != datetime.now(IST).date()
            except Exception:
                pass
    # If we get here, we'll re-check after LTP fill (below).
    return False  # provisional

# -----------------------------
# Fetch LTPs (batch)
# -----------------------------
def fetch_ltp_batch(symbols):
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

symbols = df["Symbol"].dropna().astype(str).tolist()
ltp_map = fetch_ltp_batch(symbols)
df["LTP"] = df["Symbol"].map(lambda s: ltp_map.get(s, np.nan))

# After LTPs arrive, finalize freshness decision
fresh_ok = not looks_stale(df)
if "LTP" in df.columns:
    if df["LTP"].isna().all() or (df["LTP"] == 0).all():
        fresh_ok = False

badge = "🟢 LIVE" if fresh_ok else "🔴 STALE"
st.markdown(f"### Data Status: {badge}")

# Optional: show a sheet-level "last updated" if your writer sets H1
try:
    import gspread
    from google.oauth2.service_account import Credentials
    sa_json = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(
        sa_json,
        scopes=["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    )
    gc = gspread.authorize(creds)
    # Convert CSV export URL to edit URL to read cells (works for published sheets)
    edit_url = csv_url.replace("/export?format=csv", "/edit")
    ws_ls = gc.open_by_url(edit_url).sheet1
    try:
        last_updated_cell = ws_ls.acell("H1").value  # <-- have your writer populate this
        if last_updated_cell:
            st.sidebar.caption(f"📅 TMV sheet last updated (H1): {last_updated_cell}")
    except Exception:
        pass
except Exception as e:
    st.sidebar.caption(f"ℹ️ Freshness meta not available: {e}")

# -----------------------------
# Display table
# -----------------------------
st.dataframe(df, use_container_width=True)

# -----------------------------
# TMV Explainer (on-demand live OHLC)
# -----------------------------
from fetch_ohlc import fetch_ohlc_data, calculate_indicators
st.markdown("---")
st.subheader("📘 TMV Explainer")

if not df.empty:
    sel = st.selectbox("Select a stock", df["Symbol"])
    if sel:
        sym_for_fetch = sel.replace("_", "-")
        try:
            df15 = fetch_ohlc_data(sym_for_fetch, "15minute", 7)
            indicators = calculate_indicators(df15)
            for name, val in indicators.items():
                st.markdown(f"**{name}:** {round(val,3) if isinstance(val,(int,float)) else val}")
        except Exception as e:
            st.error(f"Failed to compute indicators for {sel}: {e}")
