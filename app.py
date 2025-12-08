# app.py

import logging
from datetime import datetime

import numpy as np
import pandas as pd
import pytz
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from kiteconnect import KiteConnect

from utils.token_panel import render_token_panel
from utils.token_utils import load_credentials_from_gsheet, get_gsheet_client
from utils.fetch_ohlc import fetch_ohlc_data, calculate_indicators

# -----------------------------
# Basic config
# -----------------------------
st.set_page_config(page_title="TMV Stock Ranker", page_icon="📊", layout="wide")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("tmv_app")

IST = pytz.timezone("Asia/Kolkata")
WORKBOOK_NAME = "BackgroundAnalysisStore"
LIVESCORES_SHEET = "LiveScores"
MAX_STALENESS_MIN = 20  # Hard stop if TMV older than this many minutes

# Auto-refresh every 60s
st_autorefresh(interval=60_000, key="tmv_auto_refresh")


# -----------------------------
# Google Sheets: LiveScores
# -----------------------------
@st.cache_data(ttl=10)
def fetch_livescores_df() -> pd.DataFrame:
    """Read TMV table from BackgroundAnalysisStore / LiveScores."""
    client = get_gsheet_client()
    ws = client.open(WORKBOOK_NAME).worksheet(LIVESCORES_SHEET)
    values = ws.get_all_values()

    if not values:
        return pd.DataFrame()

    header, *rows = values
    df = pd.DataFrame(rows, columns=header)
    return df


def parse_asof(df: pd.DataFrame):
    """Parse AsOf column and return latest IST timestamp, or None if missing/invalid."""
    if "AsOf" not in df.columns:
        return None

    s = pd.to_datetime(df["AsOf"], errors="coerce")
    s = s.dropna()
    if s.empty:
        return None

    ts = s.max()
    if ts.tzinfo is None:
        ts = IST.localize(ts)

    return ts.astimezone(IST)


def freshness_badge(as_of: datetime):
    now = datetime.now(IST)
    age_min = (now - as_of).total_seconds() / 60.0

    if age_min <= 5:
        return f"🟢 LIVE ({age_min:.1f} min ago)", "green"
    elif age_min <= MAX_STALENESS_MIN:
        return f"🟡 LATE ({age_min:.1f} min ago)", "orange"
    else:
        return f"🔴 STALE ({age_min:.1f} min ago)", "red"


# -----------------------------
# Zerodha LTP helper
# -----------------------------
def add_live_ltp(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add LTP and % Change columns using Zerodha Kite LTP API.
    Uses your sheet-based credentials (ZerodhaTokenStore).
    """
    df = df.copy()
    if "Symbol" not in df.columns or df.empty:
        return df

    try:
        api_key, api_secret, access_token = load_credentials_from_gsheet()
        if not api_key or not access_token:
            st.warning("⚠️ Missing Zerodha API Key or Access Token in ZerodhaTokenStore.")
            return df

        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)

        symbols = df["Symbol"].astype(str).tolist()
        instruments = [f"NSE:{s.replace('_', '-')}" for s in symbols]

        # Zerodha allows bulk ltp calls; chunk to be safe
        all_ltp = {}
        chunk_size = 150
        for i in range(0, len(instruments), chunk_size):
            chunk = instruments[i:i + chunk_size]
            data = kite.ltp(chunk)
            all_ltp.update(data)

        ltps = []
        pct_changes = []
        for sym in symbols:
            key = f"NSE:{sym.replace('_', '-')}"
            info = all_ltp.get(key, {})
            last_price = info.get("last_price")
            ohlc = info.get("ohlc") or {}
            prev_close = ohlc.get("close") or np.nan

            if last_price is None:
                ltps.append(np.nan)
                pct_changes.append(np.nan)
            else:
                ltps.append(last_price)
                if prev_close and not np.isnan(prev_close):
                    pct_changes.append((last_price - prev_close) / prev_close * 100.0)
                else:
                    pct_changes.append(np.nan)

        df["LTP"] = ltps
        df["% Change"] = pct_changes

    except Exception as e:
        st.warning(f"⚠️ Could not fetch live LTPs from Zerodha: {e}")

    return df


# -----------------------------
# Sidebar: Token panel
# -----------------------------
with st.sidebar:
    st.header("🔐 Zerodha Token")
    render_token_panel()


# -----------------------------
# Main app
# -----------------------------
st.title("📊 TMV Stock Ranker Dashboard")
st.caption("TMV scores from Google Sheets + live prices from Zerodha. Option A: Sheet is the source of truth.")

df = fetch_livescores_df()
if df.empty or "Symbol" not in df.columns:
    st.error("❌ LiveScores sheet is empty or missing 'Symbol' column.")
    st.stop()

# Enforce freshness
as_of = parse_asof(df)
if as_of is None:
    st.error("🛑 LiveScores has no valid AsOf timestamps. Refusing to show data (freshness unknown).")
    st.stop()

now_ist = datetime.now(IST)
age_min = (now_ist - as_of).total_seconds() / 60.0
if age_min > MAX_STALENESS_MIN:
    st.error(
        f"🛑 LiveScores is {age_min:.1f} minutes old (limit: {MAX_STALENESS_MIN} min). "
        "Data is stale — refusing to load."
    )
    st.stop()

badge_text, badge_color = freshness_badge(as_of)

col_badge, col_time = st.columns([2, 1])
with col_badge:
    st.markdown(
        f"""
        <div style="padding:0.4rem 0.8rem;border-radius:0.5rem;
                    background-color:{badge_color};color:white;
                    display:inline-block;font-weight:bold;">
            {badge_text}
        </div>
        """,
        unsafe_allow_html=True,
    )
with col_time:
    st.write(f"**As of:** {as_of.strftime('%Y-%m-%d %H:%M:%S')} IST")

st.markdown("---")

# Numeric conversion for TMV columns
for col in ["TMV Score", "Trend Score", "Momentum Score", "Volume Score"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# Add live LTP and %Change
df_live = add_live_ltp(df)

# Sort by TMV Score if available
if "TMV Score" in df_live.columns:
    df_live = df_live.sort_values(by="TMV Score", ascending=False, na_position="last")

# Pretty formatting
df_disp = df_live.copy()
for col in ["TMV Score", "Trend Score", "Momentum Score", "Volume Score", "% Change"]:
    if col in df_disp.columns:
        df_disp[col] = df_disp[col].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")

if "LTP" in df_disp.columns:
    df_disp["LTP"] = df_disp["LTP"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")

st.subheader("TMV Snapshot")
st.dataframe(df_disp, use_container_width=True, hide_index=True)

st.markdown("---")
st.subheader("📘 TMV Explainer")

if not df.empty:
    sel = st.selectbox("Select a stock", df["Symbol"])
    if sel:
        sym_for_fetch = sel.replace("_", "-")
        try:
            df15 = fetch_ohlc_data(sym_for_fetch, "15minute", 7)
            if df15 is None or df15.empty:
                st.warning("No OHLC data for this symbol.")
            else:
                ind = calculate_indicators(df15)
                if not ind:
                    st.info("Could not compute indicators for this symbol.")
                else:
                    expl_df = pd.DataFrame(
                        {"Indicator": list(ind.keys()), "Value": list(ind.values())}
                    )
                    st.table(expl_df)
        except Exception as e:
            st.error(f"Failed to compute indicators for {sel}: {e}")
