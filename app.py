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
# CONFIG FALLBACKS (edit only if secrets are missing)
# ─────────────────────────────────────────────────────────────
DEFAULT_BACKGROUND_SHEET_KEY = "1Cpgj1M_ofN1SqvuqDDHuN7Gy17tfkhy4fCCP8Mx7bRI"

# 🔥 PASTE your ZerodhaTokenStore Sheet KEY here ONLY if you don't want to add it in Streamlit secrets
DEFAULT_ZERODHA_TOKEN_SHEET_KEY = ""  # <-- put your sheet key here if secrets missing

DEFAULT_ZERODHA_TOKEN_WORKSHEET = "Sheet1"
DEFAULT_LIVESCORE_WORKSHEET = "LiveScores"

# ─────────────────────────────────────────────────────────────
# Env bridge (so utils can read)
# ─────────────────────────────────────────────────────────────
def _secrets_get(key: str, default=""):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default

# Make sure required env vars exist for utils/*
if _secrets_get("GOOGLE_SERVICE_ACCOUNT_JSON", ""):
    os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"] = _secrets_get("GOOGLE_SERVICE_ACCOUNT_JSON")

# ZerodhaTokenStore routing
zerodha_sheet_key = _secrets_get("ZERODHA_TOKEN_SHEET_KEY", "") or DEFAULT_ZERODHA_TOKEN_SHEET_KEY
zerodha_ws_name = _secrets_get("ZERODHA_TOKEN_WORKSHEET", DEFAULT_ZERODHA_TOKEN_WORKSHEET)

if zerodha_sheet_key:
    os.environ["ZERODHA_TOKEN_SHEET_KEY"] = zerodha_sheet_key
os.environ["ZERODHA_TOKEN_WORKSHEET"] = zerodha_ws_name

# BackgroundAnalysisStore routing
background_sheet_key = _secrets_get("BACKGROUND_SHEET_KEY", "") or DEFAULT_BACKGROUND_SHEET_KEY
os.environ["BACKGROUND_SHEET_KEY"] = background_sheet_key
os.environ["LIVESCORE_WORKSHEET"] = _secrets_get("LIVESCORE_WORKSHEET", DEFAULT_LIVESCORE_WORKSHEET)

# ─────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("tmv_dashboard")

IST = pytz.timezone("Asia/Kolkata")
st.set_page_config(page_title="TMV Stock Ranker", page_icon="📈", layout="wide")

# ─────────────────────────────────────────────────────────────
# Hard-stop if service account JSON missing (otherwise gspread will fail)
# ─────────────────────────────────────────────────────────────
if not os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"):
    st.error("Missing GOOGLE_SERVICE_ACCOUNT_JSON in Streamlit secrets/env. Add it as a secret.")
    st.stop()

# ─────────────────────────────────────────────────────────────
# Helper: extract request_token from URL or token
# ─────────────────────────────────────────────────────────────
def extract_request_token(text: str) -> str:
    if not text:
        return ""
    t = text.strip()
    m = re.search(r"request_token=([A-Za-z0-9]+)", t)
    if m:
        return m.group(1)
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
# Zerodha session
# ─────────────────────────────────────────────────────────────
st.sidebar.header("🔐 Zerodha Session")

@st.cache_data(ttl=3600, show_spinner=False)
def load_zerodha_creds_cached():
    return load_credentials_from_gsheet()

def kite_login_flow(api_key: str, api_secret: str) -> str:
    if not api_key or not api_secret:
        st.sidebar.error("ZerodhaTokenStore missing API key/secret (A1/B1).")
        return ""

    kite_tmp = KiteConnect(api_key=api_key)
    login_url = kite_tmp.login_url()

    st.sidebar.markdown("### Login required")
    st.sidebar.markdown(f"[👉 Click to login Zerodha]({login_url})")
    st.sidebar.caption("After login, paste the full redirect URL here (or just request_token).")

    pasted = st.sidebar.text_input("Paste redirect URL or request_token", value="")
    request_token = extract_request_token(pasted)

    col1, col2 = st.sidebar.columns(2)
    go = col1.button("Generate access token", use_container_width=True)
    clr = col2.button("Clear", use_container_width=True)

    if clr:
        st.rerun()

    if not go:
        return ""

    if not request_token:
        st.sidebar.error("Could not find request_token in pasted text.")
        return ""

    try:
        sess = kite_tmp.generate_session(request_token, api_secret=api_secret)
        new_token = sess.get("access_token", "")
        if not new_token:
            st.sidebar.error("No access_token returned by Kite.")
            return ""
        save_token_to_gsheet(new_token)
        st.sidebar.success("✅ Token generated & saved to ZerodhaTokenStore (C1).")
        return new_token
    except Exception as e:
        st.sidebar.error(f"❌ Zerodha login failed: {e}")
        return ""

# Make config issues obvious
if not zerodha_sheet_key:
    st.sidebar.warning("ZERODHA_TOKEN_SHEET_KEY is missing.")
    st.sidebar.info("Fix: add ZERODHA_TOKEN_SHEET_KEY in Streamlit secrets, OR paste it in DEFAULT_ZERODHA_TOKEN_SHEET_KEY in app.py.")
    st.stop()

kite = None
api_key = api_secret = access_token = ""

try:
    api_key, api_secret, access_token = load_zerodha_creds_cached()
    if not api_key:
        raise RuntimeError("Missing api_key in ZerodhaTokenStore A1.")
    if not api_secret:
        raise RuntimeError("Missing api_secret in ZerodhaTokenStore B1.")
    if not access_token:
        raise RuntimeError("Missing access_token in ZerodhaTokenStore C1.")

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    profile = kite.profile()
    st.sidebar.success(f"✅ Logged in: {profile.get('user_name','?')} ({profile.get('user_id','?')})")

except Exception as e:
    st.sidebar.warning("⚠️ Stored token invalid/expired OR missing. Login again.")
    st.sidebar.caption(str(e))

    new_token = kite_login_flow(api_key, api_secret)
    if not new_token:
        st.stop()

    st.cache_data.clear()
    st.rerun()

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
# Load LiveScores
# ─────────────────────────────────────────────────────────────
BACKGROUND_SHEET_KEY = background_sheet_key
LIVESCORE_WS = os.getenv("LIVESCORE_WORKSHEET", DEFAULT_LIVESCORE_WORKSHEET)

st.sidebar.subheader("🧪 Data Freshness Rules")
MAX_AGE_MIN = st.sidebar.slider("Max allowed age (minutes)", 3, 120, 20, step=1)
BLOCK_STALE = st.sidebar.checkbox("Block STALE rows", value=True)
INCLUDE_UNKNOWN = st.sidebar.checkbox("Include UNKNOWN rows", value=True)

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

for c in df.columns:
    if c in ("Symbol", "Trend Direction", "Regime", "SignalReason", "DataQuality"):
        continue
    df[c] = pd.to_numeric(df[c], errors="ignore")

# Freshness (defensive)
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

# Score column detection
score_col = next((c for c in df.columns if "tmv" in c.lower() and "score" in c.lower()), None)
if not score_col:
    st.error(f"TMV score column not found. Columns: {list(df.columns)}")
    st.stop()

df[score_col] = pd.to_numeric(df[score_col], errors="coerce")

# Filter (empty-table proof)
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

# Display
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

st.dataframe(rank_df[show_cols], use_container_width=True, hide_index=True)

# Download
csv_bytes = rank_df.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Download rankings as CSV", data=csv_bytes, file_name="tmv_rankings.csv", mime="text/csv")
