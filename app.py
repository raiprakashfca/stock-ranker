# app.py
import os
import re
import logging
from datetime import datetime

import pandas as pd
import pytz
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from kiteconnect import KiteConnect

from utils.token_utils import load_credentials_from_gsheet, save_token_to_gsheet
from utils.google_client import get_gspread_client

# ─────────────────────────────────────────────────────────────
# Env bridge (so utils can read)
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
# Helpers
# ─────────────────────────────────────────────────────────────
def extract_request_token(text: str) -> str:
    """
    Accepts:
      - full redirect URL after Kite login
      - just the request_token
    Returns request_token or "".
    """
    if not text:
        return ""
    t = text.strip()
    # If it's a URL, pull request_token=
    m = re.search(r"request_token=([A-Za-z0-9]+)", t)
    if m:
        return m.group(1)
    # Otherwise assume user pasted token directly
    if re.fullmatch(r"[A-Za-z0-9]{6,}", t):
        return t
    return ""

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

# ─────────────────────────────────────────────────────────────
# Zerodha session (cached creds; interactive fallback)
# ─────────────────────────────────────────────────────────────
st.sidebar.header("🔐 Zerodha Session")

@st.cache_data(ttl=3600, show_spinner=False)
def load_zerodha_creds_cached():
    # Reads A1 api_key, B1 api_secret, C1 access_token from ZerodhaTokenStore
    return load_credentials_from_gsheet()

def kite_login_flow(api_key: str, api_secret: str) -> str:
    """
    Returns a valid access_token (string) or "" if not obtained.
    """
    if not api_key or not api_secret:
        st.sidebar.error("ZerodhaTokenStore missing API key/secret (A1/B1).")
        return ""

    kite_tmp = KiteConnect(api_key=api_key)
    login_url = kite_tmp.login_url()

    st.sidebar.markdown("### Login required")
    st.sidebar.markdown(f"[👉 Click to login Zerodha]({login_url})")
    st.sidebar.caption("After login, paste the **full redirect URL** here (or just the request_token).")

    pasted = st.sidebar.text_input("Paste redirect URL or request_token", value="", type="default")
    request_token = extract_request_token(pasted)

    col1, col2 = st.sidebar.columns(2)
    with col1:
        go = st.button("Generate access token", use_container_width=True)
    with col2:
        clear = st.button("Clear", use_container_width=True)

    if clear:
        st.rerun()

    if not go:
        return ""

    if not request_token:
        st.sidebar.error("Could not find request_token in the pasted text.")
        return ""

    try:
        session = kite_tmp.generate_session(request_token, api_secret=api_secret)
        new_token = session.get("access_token", "")
        if not new_token:
            st.sidebar.error("generate_session worked but access_token missing.")
            return ""
        # Save to ZerodhaTokenStore C1
        save_token_to_gsheet(new_token)
        st.sidebar.success("✅ Access token generated & saved to ZerodhaTokenStore (C1).")
        return new_token
    except Exception as e:
        st.sidebar.error(f"❌ Zerodha login failed: {e}")
        return ""

# Initialize Kite
kite = None
api_key = api_secret = access_token = ""

try:
    api_key, api_secret, access_token = load_zerodha_creds_cached()

    if not api_key:
        raise RuntimeError("Missing api_key in ZerodhaTokenStore (A1).")
    if not api_secret:
        raise RuntimeError("Missing api_secret in ZerodhaTokenStore (B1).")
    if not access_token:
        raise RuntimeError("Missing access_token in ZerodhaTokenStore (C1).")

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    profile = kite.profile()
    st.sidebar.success(f"✅ Logged in: {profile.get('user_name','?')} ({profile.get('user_id','?')})")

except Exception as e:
    st.sidebar.warning("⚠️ Stored token invalid/expired OR missing. Login again.")
    st.sidebar.caption(str(e))

    # Interactive login
    new_token = kite_login_flow(api_key, api_secret)
    if not new_token:
        st.stop()

    # Validate after saving
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(new_token)
    try:
        profile = kite.profile()
        st.sidebar.success(f"✅ Logged in: {profile.get('user_name','?')} ({profile.get('user_id','?')})")
        # refresh cached creds so next rerun reads token smoothly
        st.cache_data.clear()
        st.rerun()
    except Exception as e2:
        st.sidebar.error(f"❌ Token still invalid: {e2}")
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
INCLUDE_UNKNOWN = st.sidebar.checkbox("Include UNKNOWN rows", value=True)

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

# Numeric conversion (safe)
for c in df.columns:
    if c in ("Symbol", "Trend Direction", "Regime", "SignalReason", "DataQuality"):
        continue
    df[c] = pd.to_numeric(df[c], errors="ignore")

# ─────────────────────────────────────────────────────────────
# Freshness handling (defensive)
# ─────────────────────────────────────────────────────────────
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
# Diagnostics (prevents “blank table” confusion)
# ─────────────────────────────────────────────────────────────
total = len(df)
counts = df["DataQuality"].value_counts(dropna=False).to_dict()
ok_n = int(counts.get("OK", 0))
stale_n = int(counts.get("STALE", 0))
unk_n = int(counts.get("UNKNOWN", 0))

with st.expander("🔎 Diagnostics", expanded=False):
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

# ─────────────────────────────────────────────────────────────
# Score column detection
# ─────────────────────────────────────────────────────────────
score_col = next((c for c in df.columns if "tmv" in c.lower() and "score" in c.lower()), None)
if not score_col:
    st.error(f"TMV score column not found. Columns: {list(df.columns)}")
    st.stop()

df[score_col] = pd.to_numeric(df[score_col], errors="coerce")

# ─────────────────────────────────────────────────────────────
# Filtering (empty-table proof)
# ─────────────────────────────────────────────────────────────
rank_df = df.copy()

if BLOCK_STALE:
    allowed = {"OK"}
    if INCLUDE_UNKNOWN:
        allowed.add("UNKNOWN")
    rank_df = rank_df[rank_df["DataQuality"].isin(allowed)].copy()

if rank_df.empty:
    st.warning("No rows passed freshness filters. Showing ALL rows for debugging.")
    rank_df = df.copy()

rank_df = rank_df.sort_values(by=score_col, ascending=False)

# ─────────────────────────────────────────────────────────────
# Display (safe columns)
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

csv_bytes = rank_df.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Download rankings as CSV", data=csv_bytes, file_name="tmv_rankings.csv", mime="text/csv")
