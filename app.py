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

# -------------------------------------------------
# Env bridge (so utils can read Streamlit secrets)
# -------------------------------------------------
for k in [
    "ZERODHA_TOKEN_SHEET_KEY",
    "ZERODHA_TOKEN_WORKSHEET",
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    "BACKGROUND_SHEET_KEY",
]:
    if k in st.secrets:
        os.environ[k] = st.secrets[k]

# -------------------------------------------------
# Logging
# -------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("tmv_dashboard")

IST = pytz.timezone("Asia/Kolkata")

# -------------------------------------------------
# Streamlit config
# -------------------------------------------------
st.set_page_config(
    page_title="TMV Stock Ranker",
    page_icon="📈",
    layout="wide",
)

# -------------------------------------------------
# Cached loaders (CRITICAL FOR QUOTA SAFETY)
# -------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def load_zerodha_creds_cached():
    return load_credentials_from_gsheet()


@st.cache_data(ttl=120, show_spinner=False)
def load_livescores_cached(sheet_key: str, ws_name: str) -> pd.DataFrame:
    gc = get_gspread_client()
    ws = gc.open_by_key(sheet_key).worksheet(ws_name)
    values = ws.get_all_values()

    if not values or len(values) < 2:
        raise RuntimeError(f"{ws_name} empty or unreadable")

    headers = values[0]
    rows = values[1:]
    return pd.DataFrame(rows, columns=headers)


# -------------------------------------------------
# Sidebar: Zerodha Session
# -------------------------------------------------
st.sidebar.header("🔐 Zerodha Session")

kite = None

try:
    api_key, api_secret, access_token = load_zerodha_creds_cached()

    if not api_key or not api_secret:
        raise RuntimeError("Missing api_key / api_secret in ZerodhaTokenStore")

    if not access_token:
        raise RuntimeError("Missing access_token in ZerodhaTokenStore")

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    profile = kite.profile()
    st.sidebar.success(
        f"✅ Logged in as: {profile.get('user_name','?')} ({profile.get('user_id','?')})"
    )

except Exception as e:
    st.sidebar.warning("⚠️ Zerodha login required")
    st.sidebar.caption(f"Reason: {e}")

    new_token = render_token_panel(api_key, api_secret)
    if not new_token:
        st.stop()

    # clear cached creds so new token is picked up
    load_zerodha_creds_cached.clear()

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(new_token)

    try:
        profile = kite.profile()
        st.sidebar.success(
            f"✅ Logged in as: {profile.get('user_name','?')} ({profile.get('user_id','?')})"
        )
    except Exception as e2:
        st.sidebar.error(f"❌ Token validation failed: {e2}")
        st.stop()

# -------------------------------------------------
# Auto-refresh (SAFE DEFAULTS)
# -------------------------------------------------
refresh_sec = st.sidebar.slider(
    "Auto-refresh (seconds)", 60, 600, 120, step=30
)
st_autorefresh(interval=refresh_sec * 1000, key="refresh")

# -------------------------------------------------
# Header
# -------------------------------------------------
st.title("📈 TMV Stock Ranking Dashboard (Freshness-Strict)")
now_ist = datetime.now(IST)
st.caption(
    f"🕒 Page refreshed at: {now_ist.strftime('%d %b %Y, %I:%M:%S %p IST')}"
)

# -------------------------------------------------
# Sheet config
# -------------------------------------------------
BACKGROUND_SHEET_KEY = os.getenv(
    "BACKGROUND_SHEET_KEY",
    "1Cpgj1M_ofN1SqvuqDDHuN7Gy17tfkhy4fCCP8Mx7bRI",
)
LIVESCORE_WS = os.getenv("LIVESCORE_WORKSHEET", "LiveScores")

# -------------------------------------------------
# Freshness controls
# -------------------------------------------------
st.sidebar.subheader("🧪 Data Freshness Rules")
MAX_AGE_MIN = st.sidebar.slider("Max Age (minutes)", 3, 120, 20)
HARD_BLOCK_STALE = st.sidebar.checkbox("Block stale rows", value=True)


def _parse_ist(ts):
    if not ts:
        return None
    try:
        dt = pd.to_datetime(ts, errors="coerce")
        if pd.isna(dt):
            return None
        if dt.tzinfo is None:
            return IST.localize(dt.to_pydatetime())
        return dt.tz_convert(IST).to_pydatetime()
    except Exception:
        return None


def _age_minutes(dt):
    if not dt:
        return None
    return round((now_ist - dt).total_seconds() / 60.0, 1)


# -------------------------------------------------
# Load LiveScores (CACHED)
# -------------------------------------------------
try:
    df = load_livescores_cached(BACKGROUND_SHEET_KEY, LIVESCORE_WS)
except Exception as e:
    st.error(f"❌ Could not read LiveScores: {e}")
    st.stop()

df.columns = [str(c).strip() for c in df.columns]

# numeric coercion
for c in df.columns:
    if c not in ("Symbol", "Trend Direction", "Regime"):
        df[c] = pd.to_numeric(df[c], errors="ignore")

# freshness
if "AsOf" in df.columns:
    df["AsOf_dt"] = df["AsOf"].apply(_parse_ist)
    df["AgeMin"] = df["AsOf_dt"].apply(_age_minutes)
else:
    df["AgeMin"] = None

df["DataQuality"] = df["AgeMin"].apply(
    lambda x: "OK" if x is not None and x <= MAX_AGE_MIN else "STALE"
)

# -------------------------------------------------
# Ranking logic
# -------------------------------------------------
score_candidates = [
    "TMV Score",
    "TMV score",
    "TMV_Score",
    "15m TMV Score",
]

score_col = next(
    (c for c in score_candidates if c in df.columns),
    None,
)

if not score_col:
    for c in df.columns:
        if "tmv" in c.lower() and "score" in c.lower():
            score_col = c
            break

if not score_col:
    st.error(f"TMV Score column missing. Found: {list(df.columns)}")
    st.stop()

df[score_col] = pd.to_numeric(df[score_col], errors="coerce")

rank_df = df.copy()
if HARD_BLOCK_STALE:
    rank_df = rank_df[rank_df["DataQuality"] == "OK"]

rank_df = rank_df.sort_values(by=score_col, ascending=False)

# -------------------------------------------------
# Display
# -------------------------------------------------
st.subheader(
    "✅ Ranked (fresh only)"
    if HARD_BLOCK_STALE
    else "📋 Ranked (including stale)"
)

display_cols = [
    c for c in [
        "Symbol",
        "TMV Score",
        "Confidence",
        "Trend Direction",
        "Regime",
        "Reversal Probability",
        "AsOf",
        "AgeMin",
        "DataQuality",
    ]
    if c in rank_df.columns
]

st.dataframe(
    rank_df[display_cols],
    use_container_width=True,
    hide_index=True,
)

if HARD_BLOCK_STALE:
    stale = df[df["DataQuality"] != "OK"]
    if not stale.empty:
        st.subheader("⚠️ Stale / ignored rows")
        st.dataframe(
            stale[display_cols],
            use_container_width=True,
            hide_index=True,
        )

# -------------------------------------------------
# Download
# -------------------------------------------------
st.download_button(
    "⬇️ Download CSV",
    data=rank_df.to_csv(index=False).encode("utf-8"),
    file_name="tmv_rankings.csv",
    mime="text/csv",
)
