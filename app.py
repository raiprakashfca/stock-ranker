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
api_key = ""
api_secret = ""
access_token = ""

try:
    api_key, api_secret, access_token = load_credentials_from_gsheet()

    if not api_key:
        raise RuntimeError("Missing api_key in ZerodhaTokenStore (A1).")

    if not access_token:
        raise RuntimeError("Missing access_token in ZerodhaTokenStore (C1).")

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    profile = kite.profile()
    st.sidebar.success(f"✅ Logged in as: {profile.get('user_name','?')} ({profile.get('user_id','?')})")

except Exception as e:
    # TEMP: show the real reason so debugging is not blind
    st.sidebar.error(f"⚠️ Stored token check failed: {e}")
    st.sidebar.warning("Please login again to refresh today's token.")

    # ✅ FIXED: pass api_key so login and validation use SAME key
    new_token = render_token_panel(api_key)
    if not new_token:
        st.stop()

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(new_token)

    try:
        profile = kite.profile()
        st.sidebar.success(f"✅ Logged in as: {profile.get('user_name','?')} ({profile.get('user_id','?')})")
    except Exception as e2:
        st.sidebar.error(f"❌ Token still invalid after login: {e2}")
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
# Read LiveScores via gspread
# -----------------------------
try:
    gc = get_gspread_client()
    ws = gc.open_by_key(BACKGROUND_SHEET_KEY).worksheet(LIVESCORE_WS)
    values = ws.get_all_values()
    if not values or len(values) < 2:
        raise RuntimeError(f"{LIVESCORE_WS} seems empty.")

    headers = values[0]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=headers)

except Exception as e:
    st.error(f"❌ Could not read {LIVESCORE_WS} via gspread: {e}")
    st.stop()

# -----------------------------
# Type cleanup
# -----------------------------
df.columns = [str(c).strip() for c in df.columns]

for c in df.columns:
    if c in ("Symbol", "Trend Direction", "Regime", "DataQuality"):
        continue
    df[c] = pd.to_numeric(df[c], errors="ignore")

# -----------------------------
# Freshness rules
# -----------------------------
if "AsOf" in df.columns:
    df["AsOf_dt"] = df["AsOf"].apply(_parse_ist)
    df["AgeMin"] = df["AsOf_dt"].apply(_age_minutes)
else:
    df["AsOf_dt"] = None
    df["AgeMin"] = None


def _data_quality(row):
    age = row.get("AgeMin", None)
    if age is None:
        return "UNKNOWN"
    if age <= MAX_AGE_MIN:
        return "OK"
    return "STALE"


df["DataQuality"] = df.apply(_data_quality, axis=1)

# -----------------------------
# Ranking
# -----------------------------
score_candidates = ["TMV Score", "TMV score", "TMV_Score", "15m TMV Score", "15m TMV score"]

score_col = next((c for c in score_candidates if c in df.columns), None)
if score_col is None:
    for c in df.columns:
        cl = c.lower()
        if "tmv" in cl and "score" in cl:
            score_col = c
            break

if score_col is None:
    st.error(f"LiveScores missing TMV score column. Found columns: {list(df.columns)}")
    st.stop()

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
for col in [
    "Symbol", "TMV Score", "Confidence", "Trend Direction", "Regime",
    "Reversal Probability", "AsOf", "CandleTime", "AgeMin", "DataQuality"
]:
    if col in rank_df.columns:
        show_cols.append(col)

if not show_cols:
    show_cols = rank_df.columns.tolist()

st.dataframe(rank_df[show_cols], use_container_width=True, hide_index=True)

if HARD_BLOCK_STALE:
    stale = df[df["DataQuality"] != "OK"].copy()
    if not stale.empty:
        st.subheader("⚠️ Stale / Unknown rows (NOT used for ranking)")
        st.dataframe(stale[show_cols], use_container_width=True, hide_index=True)

csv_bytes = rank_df.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Download table as CSV", data=csv_bytes, file_name="tmv_rankings.csv", mime="text/csv")
