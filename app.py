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
# Environment bridge
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
st.set_page_config(page_title="TMV Stock Ranker", page_icon="📈", layout="wide")

# ─────────────────────────────────────────────────────────────
# Zerodha session (cached)
# ─────────────────────────────────────────────────────────────
st.sidebar.header("🔐 Zerodha Session")

@st.cache_data(ttl=3600, show_spinner=False)
def load_zerodha_creds_cached():
    return load_credentials_from_gsheet()

kite = None
api_key = ""
api_secret = ""
access_token = ""

try:
    api_key, api_secret, access_token = load_zerodha_creds_cached()

    if not api_key or not access_token:
        raise RuntimeError("Missing Zerodha credentials.")

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    profile = kite.profile()

    st.sidebar.success(
        f"✅ Logged in as: {profile.get('user_name','?')} ({profile.get('user_id','?')})"
    )

except Exception as e:
    st.sidebar.warning("⚠️ Stored token invalid or expired.")
    st.sidebar.caption(str(e))

    # ✅ REVERTED: original working behavior
    new_token = render_token_panel()
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
# Auto-refresh
# ─────────────────────────────────────────────────────────────
refresh_sec = st.sidebar.slider("Auto-refresh (seconds)", 60, 600, 120, step=30)
st_autorefresh(interval=refresh_sec * 1000, key="refresh")

# ─────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────
st.title("📈 TMV Stock Ranking Dashboard")
now_ist = datetime.now(IST)
st.caption(f"🕒 Page refreshed at: {now_ist.strftime('%d %b %Y, %I:%M:%S %p IST')}")

# ─────────────────────────────────────────────────────────────
# Sheets config
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
# Cached LiveScores reader
# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def load_livescores():
    gc = get_gspread_client()
    ws = gc.open_by_key(BACKGROUND_SHEET_KEY).worksheet(LIVESCORE_WS)
    values = ws.get_all_values()
    if not values or len(values) < 2:
        raise RuntimeError("LiveScores empty")
    return pd.DataFrame(values[1:], columns=values[0])

try:
    df = load_livescores()
except Exception as e:
    st.error(f"❌ Could not read LiveScores: {e}")
    st.stop()

df.columns = [str(c).strip() for c in df.columns]

for c in df.columns:
    if c not in ("Symbol", "Trend Direction", "Regime", "SignalReason", "DataQuality"):
        df[c] = pd.to_numeric(df[c], errors="ignore")

def parse_ist(ts):
    try:
        dt = pd.to_datetime(ts, errors="coerce")
        if pd.isna(dt):
            return None
        return IST.localize(dt.to_pydatetime()) if dt.tzinfo is None else dt.tz_convert(IST)
    except Exception:
        return None

df["AsOf_dt"] = df["AsOf"].apply(parse_ist)
df["AgeMin"] = df["AsOf_dt"].apply(
    lambda d: round((now_ist - d).total_seconds() / 60, 1) if d else None
)

df["DataQuality"] = df["AgeMin"].apply(
    lambda a: "OK" if a is not None and a <= MAX_AGE_MIN else "STALE"
)

score_col = next(c for c in df.columns if "tmv" in c.lower() and "score" in c.lower())
rank_df = df[df["DataQuality"] == "OK"] if HARD_BLOCK_STALE else df
rank_df = rank_df.sort_values(by=score_col, ascending=False)

st.dataframe(
    rank_df[
        ["Symbol", score_col, "Confidence", "Trend Direction", "Regime",
         "SignalReason", "Reversal Probability", "AgeMin", "DataQuality"]
    ],
    use_container_width=True,
    hide_index=True,
)
