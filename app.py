import os, json, logging
import numpy as np
import pandas as pd
import pytz
from datetime import datetime
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from kiteconnect import KiteConnect

from utils.token_panel import render_token_panel
from utils.token_utils import load_credentials_from_gsheet
from utils.google_client import get_gspread_client

# -----------------------------
# Env bridge (so utils can read)
# -----------------------------
if "ZERODHA_TOKEN_SHEET_KEY" in st.secrets:
    os.environ["ZERODHA_TOKEN_SHEET_KEY"] = st.secrets["ZERODHA_TOKEN_SHEET_KEY"]
if "ZERODHA_TOKEN_WORKSHEET" in st.secrets:
    os.environ["ZERODHA_TOKEN_WORKSHEET"] = st.secrets["ZERODHA_TOKEN_WORKSHEET"]
if "GOOGLE_SERVICE_ACCOUNT_JSON" in st.secrets:
    os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"] = st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"]
if "BACKGROUND_SHEET_KEY" in st.secrets:
    os.environ["BACKGROUND_SHEET_KEY"] = st.secrets["BACKGROUND_SHEET_KEY"]

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("tmv_dashboard")

IST = pytz.timezone("Asia/Kolkata")

# -----------------------------
# Streamlit config
# -----------------------------
st.set_page_config(page_title="TMV Stock Ranker", page_icon="📈", layout="wide")

# -----------------------------
# Sidebar: Zerodha session
# -----------------------------
st.sidebar.header("🔐 Zerodha Session")

kite = None
try:
    api_key, api_secret, access_token = load_credentials_from_gsheet()
    if not api_key or not access_token:
        raise RuntimeError("Missing API key or access token in ZerodhaTokenStore.")

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    profile = kite.profile()
    st.sidebar.success(f"✅ Logged in as: {profile.get('user_name','?')} ({profile.get('user_id','?')})")

except Exception as e:
    st.sidebar.warning("⚠️ Stored token invalid/expired. Please login again.")
    access_token = render_token_panel()
    if not access_token:
        st.stop()

    api_key = st.secrets.get("Zerodha_API_Key", "")
    if not api_key:
        st.error("Missing Zerodha_API_Key in Streamlit secrets.")
        st.stop()

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    try:
        profile = kite.profile()
        st.sidebar.success(f"✅ Logged in as: {profile.get('user_name','?')} ({profile.get('user_id','?')})")
    except Exception:
        st.error("Token still invalid. Re-generate token.")
        st.stop()

# -----------------------------
# Auto-refresh
# -----------------------------
refresh_sec = st.sidebar.slider("Auto-refresh (seconds)", 30, 300, 60, step=30)
st_autorefresh(interval=refresh_sec * 1000, key="refresh")

# -----------------------------
# Header
# -----------------------------
st.title("📈 TMV Stock Ranking Dashboard (Freshness-Strict)")
now_ist = datetime.now(IST)
st.caption(f"🕒 Page refreshed at: {now_ist.strftime('%d %b %Y, %I:%M:%S %p IST')}")

# -----------------------------
# Sheet config (BackgroundAnalysisStore)
# -----------------------------
BACKGROUND_SHEET_KEY = os.getenv(
    "BACKGROUND_SHEET_KEY",
    # fallback to your current sheet id used in app.py CSV url
    "1Cpgj1M_ofN1SqvuqDDHuN7Gy17tfkhy4fCCP8Mx7bRI",
)
LIVESCORE_WS = os.getenv("LIVESCORE_WORKSHEET", "LiveScores")

# Freshness thresholds
st.sidebar.subheader("🧪 Data Freshness Rules")
MAX_AGE_MIN = st.sidebar.slider("Max allowed Age (minutes)", 3, 120, 20, step=1)
HARD_BLOCK_STALE = st.sidebar.checkbox("Block stale rows from ranking", value=True)

def _parse_ist(ts):
    """Parse timestamp to IST aware datetime; return None if invalid."""
    if ts is None or (isinstance(ts, float) and np.isnan(ts)):
        return None
    try:
        dt = pd.to_datetime(ts, errors="coerce")
        if pd.isna(dt):
            return None
        if getattr(dt, "tzinfo", None) is None:
            dt = IST.localize(dt.to_pydatetime())
        else:
            dt = dt.tz_convert(IST).to_pydatetime()
        return dt
    except Exception:
        return None

def _age_minutes(dt_ist):
    if not dt_ist:
        return None
    return round((now_ist - dt_ist).total_seconds() / 60.0, 1)

# -----------------------------
# Read LiveScores properly (NO gid=0 / sheet1 nonsense)
# -----------------------------
df = pd.DataFrame()
meta_msg = None
try:
    gc = get_gspread_client()
    ws = gc.open_by_key(BACKGROUND_SHEET_KEY).worksheet(LIVESCORE_WS)
    values = ws.get_all_values()
    if not values or len(values) < 2:
        raise RuntimeError(f"{LIVESCORE_WS} seems empty.")

    headers = values[0]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=headers)

    # try to show the watchdog timestamp if present
    # (we’ll keep it optional; row-wise freshness is the source of truth)
    try:
        h1 = ws.acell("H1").value
        if h1:
            st.sidebar.caption(f"📌 Watchdog (H1): {h1}")
    except Exception:
        pass

except Exception as e:
    meta_msg = f"❌ Could not read {LIVESCORE_WS} via gspread: {e}"
    st.error(meta_msg)
    st.stop()

# -----------------------------
# Type cleanup
# -----------------------------
for c in df.columns:
    if c in ("Symbol", "Trend Direction", "Regime", "DataQuality"):
        continue
    df[c] = pd.to_numeric(df[c], errors="ignore")

# -----------------------------
# Enforce row-wise freshness
# Expecting columns written by tmv_updater:
#   AsOf (IST ISO), CandleTime (last candle time), etc.
# -----------------------------
if "AsOf" in df.columns:
    df["AsOf_dt"] = df["AsOf"].apply(_parse_ist)
    df["AgeMin"] = df["AsOf_dt"].apply(_age_minutes)
else:
    df["AsOf_dt"] = None
    df["AgeMin"] = None

if "CandleTime" in df.columns:
    df["Candle_dt"] = df["CandleTime"].apply(_parse_ist)
else:
    df["Candle_dt"] = None

def _data_quality(row):
    age = row.get("AgeMin", None)
    if age is None:
        return "UNKNOWN"
    if age <= MAX_AGE_MIN:
        return "OK"
    return "STALE"

df["DataQuality"] = df.apply(_data_quality, axis=1)

# -----------------------------
# Ranking logic: block stale rows if enabled
# -----------------------------
score_col = "TMV Score"
if score_col not in df.columns:
    st.error(f"LiveScores missing '{score_col}' column. Fix tmv_updater writer.")
    st.stop()

# make TMV numeric
df[score_col] = pd.to_numeric(df[score_col], errors="coerce")

rank_df = df.copy()
if HARD_BLOCK_STALE:
    rank_df = rank_df[rank_df["DataQuality"] == "OK"].copy()

rank_df = rank_df.sort_values(by=score_col, ascending=False)

# -----------------------------
# Display
# -----------------------------
st.subheader("✅ Ranked (fresh rows only)" if HARD_BLOCK_STALE else "📋 Ranked (includes stale rows)")

show_cols = []
for col in ["Symbol", "TMV Score", "Confidence", "Trend Direction", "Regime", "Reversal Probability",
            "AsOf", "CandleTime", "AgeMin", "DataQuality"]:
    if col in rank_df.columns:
        show_cols.append(col)

if not show_cols:
    show_cols = rank_df.columns.tolist()

st.dataframe(rank_df[show_cols], use_container_width=True, hide_index=True)

# Show stale rows separately if we blocked them
if HARD_BLOCK_STALE:
    stale = df[df["DataQuality"] != "OK"].copy()
    if not stale.empty:
        st.subheader("⚠️ Stale / Unknown rows (NOT used for ranking)")
        st.dataframe(stale[show_cols], use_container_width=True, hide_index=True)

# Download
csv_bytes = rank_df.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Download table as CSV", data=csv_bytes, file_name="tmv_rankings.csv", mime="text/csv")
