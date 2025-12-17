# app.py
import os
import logging
from datetime import datetime

import pandas as pd
import pytz
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from kiteconnect import KiteConnect

from utils.token_panel import render_token_panel
from utils.token_utils import load_credentials_from_gsheet
from utils.google_client import get_gspread_client

# ─────────────────────────────────────────────────────────────
# Env bridge
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

st.set_page_config(page_title="TMV Stock Ranker", page_icon="📈", layout="wide")

# ─────────────────────────────────────────────────────────────
# Zerodha session (cached)
# ─────────────────────────────────────────────────────────────
st.sidebar.header("🔐 Zerodha Session")

@st.cache_data(ttl=3600, show_spinner=False)
def load_zerodha_creds_cached():
    return load_credentials_from_gsheet()

api_key = ""
api_secret = ""
access_token = ""

try:
    api_key, api_secret, access_token = load_zerodha_creds_cached()
    if not api_key or not access_token:
        raise RuntimeError("Missing API key or access token in ZerodhaTokenStore")

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    profile = kite.profile()
    st.sidebar.success(f"✅ Logged in as: {profile.get('user_name','?')} ({profile.get('user_id','?')})")

except Exception as e:
    st.sidebar.warning("⚠️ Stored token invalid/expired. Login again.")
    st.sidebar.caption(str(e))

    new_token = render_token_panel()
    if not new_token:
        st.stop()

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(new_token)

    try:
        profile = kite.profile()
        st.sidebar.success(f"✅ Logged in as: {profile.get('user_name','?')} ({profile.get('user_id','?')})")
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
# Sheet config
# ─────────────────────────────────────────────────────────────
BACKGROUND_SHEET_KEY = os.getenv(
    "BACKGROUND_SHEET_KEY",
    "1Cpgj1M_ofN1SqvuqDDHuN7Gy17tfkhy4fCCP8Mx7bRI",
)
LIVESCORE_WS = os.getenv("LIVESCORE_WORKSHEET", "LiveScores")

# ─────────────────────────────────────────────────────────────
# Freshness controls
# ─────────────────────────────────────────────────────────────
st.sidebar.subheader("🧪 Data Freshness Rules")
MAX_AGE_MIN = st.sidebar.slider("Max allowed age (minutes)", 3, 120, 20, step=1)
BLOCK_STALE = st.sidebar.checkbox("Block STALE rows", value=True)
INCLUDE_UNKNOWN = st.sidebar.checkbox("Include UNKNOWN rows (recommended)", value=True)

# ─────────────────────────────────────────────────────────────
# Read LiveScores (cached)
# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def load_livescores():
    gc = get_gspread_client()
    ws = gc.open_by_key(BACKGROUND_SHEET_KEY).worksheet(LIVESCORE_WS)
    values = ws.get_all_values()
    if not values or len(values) < 2:
        raise RuntimeError("LiveScores is empty (no rows).")
    return pd.DataFrame(values[1:], columns=values[0])

try:
    df = load_livescores()
except Exception as e:
    st.error(f"❌ Could not read LiveScores: {e}")
    st.stop()

df.columns = [str(c).strip() for c in df.columns]

# numeric conversion (safe)
for c in df.columns:
    if c in ("Symbol", "Trend Direction", "Regime", "SignalReason", "DataQuality"):
        continue
    df[c] = pd.to_numeric(df[c], errors="ignore")

# ─────────────────────────────────────────────────────────────
# Freshness handling (defensive)
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

if "AsOf" in df.columns:
    freshness_src = "AsOf"
elif "CandleTime" in df.columns:
    freshness_src = "CandleTime"
else:
    freshness_src = None

df["AsOf_dt"] = df[freshness_src].apply(parse_ist) if freshness_src else None
df["AgeMin"] = df["AsOf_dt"].apply(
    lambda d: round((now_ist - d).total_seconds() / 60, 1) if d else None
)

def quality(age):
    if age is None:
        return "UNKNOWN"
    return "OK" if age <= MAX_AGE_MIN else "STALE"

df["DataQuality"] = df["AgeMin"].apply(quality)

# ─────────────────────────────────────────────────────────────
# Diagnostics (so you never stare at an empty table again)
# ─────────────────────────────────────────────────────────────
total = len(df)
counts = df["DataQuality"].value_counts(dropna=False).to_dict()
ok_n = int(counts.get("OK", 0))
stale_n = int(counts.get("STALE", 0))
unk_n = int(counts.get("UNKNOWN", 0))

with st.expander("🔎 Diagnostics (why table may be empty)", expanded=True):
    st.write(
        {
            "rows_total": total,
            "freshness_source": freshness_src,
            "OK": ok_n,
            "STALE": stale_n,
            "UNKNOWN": unk_n,
            "columns": list(df.columns),
        }
    )
    if freshness_src:
        try:
            st.write("Latest timestamp sample:", df[freshness_src].dropna().head(3).tolist())
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────
# Score column detection
# ─────────────────────────────────────────────────────────────
score_col = next((c for c in df.columns if "tmv" in c.lower() and "score" in c.lower()), None)
if not score_col:
    st.error(f"TMV score column not found. Columns: {list(df.columns)}")
    st.stop()

df[score_col] = pd.to_numeric(df[score_col], errors="coerce")

# ─────────────────────────────────────────────────────────────
# Filtering logic (empty-table proof)
# ─────────────────────────────────────────────────────────────
rank_df = df.copy()

if BLOCK_STALE:
    allowed = {"OK"}
    if INCLUDE_UNKNOWN:
        allowed.add("UNKNOWN")
    rank_df = rank_df[rank_df["DataQuality"].isin(allowed)].copy()

# If still empty, force-show everything (better than blank)
if rank_df.empty:
    st.warning("No rows passed your freshness filters. Showing ALL rows for debugging.")
    rank_df = df.copy()

rank_df = rank_df.sort_values(by=score_col, ascending=False)

# ─────────────────────────────────────────────────────────────
# Display (safe column selection)
# ─────────────────────────────────────────────────────────────
preferred_cols = [
    "Symbol",
    score_col,
    "TMV Δ",
    "Base TMV",
    "Confidence",
    "Trend Direction",
    "Regime",
    "SignalReason",
    "Reversal Probability",
    "AsOf",
    "CandleTime",
    "AgeMin",
    "DataQuality",
]
show_cols = [c for c in preferred_cols if c in rank_df.columns]
if not show_cols:
    show_cols = rank_df.columns.tolist()

st.subheader("📋 Rankings")
st.dataframe(rank_df[show_cols], use_container_width=True, hide_index=True)

# Download
csv_bytes = rank_df.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Download rankings as CSV", data=csv_bytes, file_name="tmv_rankings.csv", mime="text/csv")
