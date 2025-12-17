# app.py
import os
import logging
from datetime import datetime

import numpy as np
import pandas as pd
import pytz
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from kiteconnect import KiteConnect

from utils.token_panel import render_token_panel
from utils.token_utils import load_credentials_from_gsheet
from utils.google_client import get_gspread_client

# ─────────────────────────────────────────────────────────────
# Environment bridge (so utils work everywhere)
# ─────────────────────────────────────────────────────────────
for key in [
    "ZERODHA_TOKEN_SHEET_KEY",
    "ZERODHA_TOKEN_WORKSHEET",
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    "BACKGROUND_SHEET_KEY",
]:
    if key in st.secrets:
        os.environ[key] = st.secrets[key]

# ─────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("tmv_dashboard")

IST = pytz.timezone("Asia/Kolkata")

# ─────────────────────────────────────────────────────────────
# Streamlit config
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TMV Stock Ranker",
    page_icon="📈",
    layout="wide",
)

# ─────────────────────────────────────────────────────────────
# Zerodha session (CACHED, SAFE)
# ─────────────────────────────────────────────────────────────
st.sidebar.header("🔐 Zerodha Session")

@st.cache_data(ttl=3600, show_spinner=False)
def load_zerodha_creds_cached():
    """
    Read Zerodha credentials ONCE per hour.
    Prevents Google Sheets quota blow-ups.
    """
    return load_credentials_from_gsheet()

kite = None
api_key = ""
api_secret = ""
access_token = ""

try:
    api_key, api_secret, access_token = load_zerodha_creds_cached()

    if not api_key or not access_token:
        raise RuntimeError("Missing API key or access token in ZerodhaTokenStore.")

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    profile = kite.profile()
    st.sidebar.success(
        f"✅ Logged in as: {profile.get('user_name','?')} ({profile.get('user_id','?')})"
    )

except Exception as e:
    st.sidebar.warning("⚠️ Stored token invalid or expired.")
    st.sidebar.caption(str(e))

    # 🔑 IMPORTANT: this restores your OLD behavior
    # You can paste FULL redirect URL or just request_token
    new_token = render_token_panel(api_key)
    if not new_token:
        st.stop()

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(new_token)

    try:
        profile = kite.profile()
        st.sidebar.success(
            f"✅ Logged in as: {profile.get('user_name','?')} ({profile.get('user_id','?')})"
        )
    except Exception as e2:
        st.sidebar.error(f"❌ Zerodha login failed: {e2}")
        st.stop()

# ─────────────────────────────────────────────────────────────
# Auto-refresh (SAFE)
# ─────────────────────────────────────────────────────────────
refresh_sec = st.sidebar.slider(
    "Auto-refresh (seconds)", 60, 600, 120, step=30
)
st_autorefresh(interval=refresh_sec * 1000, key="refresh")

# ─────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────
st.title("📈 TMV Stock Ranking Dashboard")
now_ist = datetime.now(IST)
st.caption(
    f"🕒 Page refreshed at: {now_ist.strftime('%d %b %Y, %I:%M:%S %p IST')}"
)

# ─────────────────────────────────────────────────────────────
# Google Sheet config
# ─────────────────────────────────────────────────────────────
BACKGROUND_SHEET_KEY = os.getenv(
    "BACKGROUND_SHEET_KEY",
    "1Cpgj1M_ofN1SqvuqDDHuN7Gy17tfkhy4fCCP8Mx7bRI",
)
LIVESCORE_WS = os.getenv("LIVESCORE_WORKSHEET", "LiveScores")

# ─────────────────────────────────────────────────────────────
# Freshness rules
# ─────────────────────────────────────────────────────────────
st.sidebar.subheader("🧪 Data Freshness Rules")
MAX_AGE_MIN = st.sidebar.slider("Max allowed age (minutes)", 3, 120, 20, step=1)
HARD_BLOCK_STALE = st.sidebar.checkbox("Block stale rows", value=True)

# ─────────────────────────────────────────────────────────────
# Cached LiveScores reader (CRITICAL)
# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def load_livescores():
    gc = get_gspread_client()
    ws = gc.open_by_key(BACKGROUND_SHEET_KEY).worksheet(LIVESCORE_WS)
    values = ws.get_all_values()
    if not values or len(values) < 2:
        raise RuntimeError("LiveScores is empty.")
    headers = values[0]
    rows = values[1:]
    return pd.DataFrame(rows, columns=headers)

try:
    df = load_livescores()
except Exception as e:
    st.error(f"❌ Could not read LiveScores: {e}")
    st.stop()

# ─────────────────────────────────────────────────────────────
# Data cleanup
# ─────────────────────────────────────────────────────────────
df.columns = [str(c).strip() for c in df.columns]

for c in df.columns:
    if c in ("Symbol", "Trend Direction", "Regime", "SignalReason", "DataQuality"):
        continue
    df[c] = pd.to_numeric(df[c], errors="ignore")

# ─────────────────────────────────────────────────────────────
# Freshness computation
# ─────────────────────────────────────────────────────────────
def parse_ist(ts):
    try:
        dt = pd.to_datetime(ts, errors="coerce")
        if pd.isna(dt):
            return None
        if dt.tzinfo is None:
            return IST.localize(dt.to_pydatetime())
        return dt.tz_convert(IST).to_pydatetime()
    except Exception:
        return None

def age_minutes(dt):
    if not dt:
        return None
    return round((now_ist - dt).total_seconds() / 60, 1)

df["AsOf_dt"] = df["AsOf"].apply(parse_ist) if "AsOf" in df.columns else None
df["AgeMin"] = df["AsOf_dt"].apply(age_minutes)

def data_quality(row):
    age = row.get("AgeMin")
    if age is None:
        return "UNKNOWN"
    return "OK" if age <= MAX_AGE_MIN else "STALE"

df["DataQuality"] = df.apply(data_quality, axis=1)

# ─────────────────────────────────────────────────────────────
# TMV score detection
# ─────────────────────────────────────────────────────────────
score_col = None
for c in df.columns:
    cl = c.lower()
    if "tmv" in cl and "score" in cl:
        score_col = c
        break

if not score_col:
    st.error(f"TMV score column not found. Columns: {list(df.columns)}")
    st.stop()

df[score_col] = pd.to_numeric(df[score_col], errors="coerce")

rank_df = df.copy()
if HARD_BLOCK_STALE:
    rank_df = rank_df[rank_df["DataQuality"] == "OK"].copy()

rank_df = rank_df.sort_values(by=score_col, ascending=False)

# ─────────────────────────────────────────────────────────────
# Display
# ─────────────────────────────────────────────────────────────
st.subheader(
    "✅ Ranked (fresh data only)"
    if HARD_BLOCK_STALE
    else "📋 Ranked (includes stale rows)"
)

show_cols = [
    "Symbol",
    score_col,
    "Confidence",
    "Trend Direction",
    "Regime",
    "SignalReason",
    "Reversal Probability",
    "AsOf",
    "AgeMin",
    "DataQuality",
]

show_cols = [c for c in show_cols if c in rank_df.columns]

st.dataframe(
    rank_df[show_cols],
    use_container_width=True,
    hide_index=True,
)

# ─────────────────────────────────────────────────────────────
# Stale rows (diagnostic)
# ─────────────────────────────────────────────────────────────
if HARD_BLOCK_STALE:
    stale = df[df["DataQuality"] != "OK"]
    if not stale.empty:
        st.subheader("⚠️ Stale / ignored rows")
        st.dataframe(
            stale[show_cols],
            use_container_width=True,
            hide_index=True,
        )

# ─────────────────────────────────────────────────────────────
# Download
# ─────────────────────────────────────────────────────────────
csv_bytes = rank_df.to_csv(index=False).encode("utf-8")
st.download_button(
    "⬇️ Download rankings as CSV",
    data=csv_bytes,
    file_name="tmv_rankings.csv",
    mime="text/csv",
)
