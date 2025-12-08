# app.py
#
# Streamlit TMV Dashboard (Stock Ranker)
#
# - Reads precomputed TMV scores from a Google Sheet (or CSV export).
# - Fetches live LTP + % Change from Zerodha.
# - Shows token status and in-app Zerodha login panel.
# - Provides a TMV explainer using recent 15m OHLC candles.
#
# Dependencies:
#   - utils/google_client.py
#   - utils/token_store.py
#   - utils/token_panel.py
#   - utils/ohlc.py
#   - utils/indicators.py

import os
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytz
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

from kiteconnect import KiteConnect

from utils.google_client import get_gspread_client
from utils.token_store import get_kite, read_token_row
from utils.token_panel import render_token_panel
from utils.ohlc import fetch_ohlc
from utils.indicators import calculate_scores


# -----------------------------
# Basic config
# -----------------------------

st.set_page_config(
    page_title="TMV Stock Ranker",
    page_icon="📊",
    layout="wide",
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("tmv_app")

IST = pytz.timezone("Asia/Kolkata")

# Auto-refresh every 60 seconds
st_autorefresh(interval=60_000, limit=None, key="tmv_auto_refresh")


# -----------------------------
# Config helpers
# -----------------------------

def _get_live_scores_df() -> pd.DataFrame:
    """
    Load TMV table (LiveScores) from Google Sheet.

    Strategy:
    1) If LIVE_SCORES_CSV_URL is set in secrets or env, use that.
    2) Else fall back to GSpread: BackgroundAnalysisStore -> LiveScores.
    """
    csv_url = st.secrets.get("LIVE_SCORES_CSV_URL", None) or os.getenv("LIVE_SCORES_CSV_URL", "")

    if csv_url:
        try:
            df = pd.read_csv(csv_url)
            return df
        except Exception as e:
            st.warning(f"CSV URL failed ({e}), falling back to GSpread...")

    # Fallback to direct GSpread (adjust workbook/sheet as per your setup)
    try:
        client = get_gspread_client()
        sheet = client.open("BackgroundAnalysisStore").worksheet("LiveScores")
        values = sheet.get_all_values()
        if not values:
            return pd.DataFrame()
        header, *rows = values
        df = pd.DataFrame(rows, columns=header)
        return df
    except Exception as e:
        st.error(f"❌ Could not load LiveScores from Google Sheets: {e}")
        return pd.DataFrame()


def _parse_asof(df: pd.DataFrame):
    """
    Determine 'as-of' timestamp from either:
    - An 'AsOf' column (max value)
    - Or a 'Last Updated' / timestamp cell in the sheet (not implemented here).
    """
    if "AsOf" in df.columns:
        try:
            ts = pd.to_datetime(df["AsOf"]).max()
            if pd.isna(ts):
                return None
            return ts.tz_localize(IST) if ts.tzinfo is None else ts.astimezone(IST)
        except Exception:
            return None
    return None


def _compute_freshness_badge(as_of):
    if as_of is None:
        return "⚪ UNKNOWN", "gray"

    now_ist = datetime.now(IST)
    age_min = (now_ist - as_of).total_seconds() / 60.0

    if age_min <= 5:
        return f"🟢 LIVE (updated {age_min:.1f} min ago)", "green"
    elif age_min <= 15:
        return f"🟡 LATE (updated {age_min:.1f} min ago)", "orange"
    else:
        return f"🔴 STALE (updated {age_min:.1f} min ago)", "red"


# -----------------------------
# Sidebar: Token status & login
# -----------------------------

def sidebar_token_status():
    with st.sidebar:
        st.title("🔐 Zerodha Token")

        # Read token row directly
        try:
            tr = read_token_row()
            token_present = bool(tr.access_token)
            expires_at = tr.expires_at
        except Exception as e:
            st.error(f"Error reading ZerodhaTokenStore: {e}")
            token_present = False
            expires_at = None
            tr = None

        token_status = "❌ Missing"
        expiry_str = "–"

        if token_present:
            token_status = "✅ Present"
            if expires_at:
                expiry_str = expires_at.astimezone(IST).strftime("%Y-%m-%d %H:%M")
            else:
                expiry_str = "Unknown"

        st.markdown(
            f"""
            **Access Token:** {token_status}  
            **Expires At:** {expiry_str}
            """
        )

        # Quick verification
        if token_present:
            try:
                kite = get_kite(validate=True)
                profile = kite.profile()
                st.success(f"Token OK for **{profile.get('user_name', 'User')}**")
            except Exception as e:
                st.warning(f"Token seems invalid or expired: {e}")

        st.markdown("---")
        st.subheader("Token Manager")
        render_token_panel()


sidebar_token_status()


# -----------------------------
# Main Layout – Header
# -----------------------------

st.title("📊 TMV Stock Ranker Dashboard")

st.caption(
    "Precomputed TMV scores + live prices from Zerodha. "
    "Use this to quickly scan opportunities across your watchlist."
)

# -----------------------------
# Load LiveScores data
# -----------------------------

df = _get_live_scores_df()

if df.empty or "Symbol" not in df.columns:
    st.error("❌ LiveScores sheet is empty or invalid. Expecting at least a 'Symbol' column.")
    st.stop()

# Ensure numeric types where appropriate
for col in ["TMV Score", "Trend Score", "Momentum Score", "Volume Score", "Reversal Probability"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# -----------------------------
# Freshness badge
# -----------------------------

as_of = _parse_asof(df)
badge_text, badge_color = _compute_freshness_badge(as_of)

col_fresh, col_time = st.columns([2, 1])
with col_fresh:
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
    if as_of is not None:
        st.write(f"**As of:** {as_of.strftime('%Y-%m-%d %H:%M:%S')} IST")
    else:
        st.write("**As of:** unknown")

st.markdown("---")

# -----------------------------
# Live LTP + % Change using Zerodha
# -----------------------------

def add_live_ltp(df_source: pd.DataFrame) -> pd.DataFrame:
    df_local = df_source.copy()
    symbols = df_local["Symbol"].astype(str).tolist()
    if not symbols:
        return df_local

    try:
        # Normalize symbols for Zerodha (replace '_' with '-', etc.)
        symbols_kite = [s.replace("_", "-") for s in symbols]

        kite = get_kite(validate=False)

        # Zerodha ltp limit per call is high, but chunk to be safe
        all_data = {}
        chunk_size = 150
        for i in range(0, len(symbols_kite), chunk_size):
            chunk = symbols_kite[i : i + chunk_size]
            keys = [f"NSE:{s}" for s in chunk]
            data = kite.ltp(keys)
            all_data.update(data)

        ltps = []
        pct_changes = []
        for sym, sym_k in zip(symbols, symbols_kite):
            key = f"NSE:{sym_k}"
            info = all_data.get(key, {})
            last_price = info.get("last_price")
            ohlc = info.get("ohlc") or {}
            close = ohlc.get("close") or np.nan

            if last_price is None:
                ltps.append(np.nan)
                pct_changes.append(np.nan)
            else:
                ltps.append(last_price)
                if close and not np.isnan(close):
                    pct_changes.append((last_price - close) / close * 100.0)
                else:
                    pct_changes.append(np.nan)

        df_local["LTP"] = ltps
        df_local["% Change"] = pct_changes
    except Exception as e:
        st.warning(f"⚠️ Could not fetch live LTPs from Zerodha: {e}")

    return df_local


df_live = add_live_ltp(df)

# -----------------------------
# Main TMV table view
# -----------------------------

st.subheader("TMV Snapshot")

# Sort by TMV Score descending if present
if "TMV Score" in df_live.columns:
    df_live = df_live.sort_values(by="TMV Score", ascending=False, na_position="last")

# Pretty formatting for display
df_disp = df_live.copy()
for col in ["TMV Score", "Trend Score", "Momentum Score", "Volume Score", "Reversal Probability", "% Change"]:
    if col in df_disp.columns:
        df_disp[col] = df_disp[col].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")

if "LTP" in df_disp.columns:
    df_disp["LTP"] = df_disp["LTP"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")

st.dataframe(
    df_disp,
    use_container_width=True,
    hide_index=True,
)

st.markdown("---")

# -----------------------------
# TMV Explainer
# -----------------------------

st.subheader("📘 TMV Explainer")

if not df_live.empty:
    sel = st.selectbox("Select a stock", df_live["Symbol"])

    if sel:
        sym_for_fetch = sel.replace("_", "-")

        col_left, col_right = st.columns([2, 1])

        with col_left:
            st.markdown(f"### {sel} – 15m TMV Breakdown (last few days)")
            try:
                df15 = fetch_ohlc(sym_for_fetch, interval="15minute", days=7)
                if df15.empty:
                    st.warning("No OHLC data returned for this symbol.")
                else:
                    scores = calculate_scores(df15)
                    if not scores:
                        st.info("Could not compute TMV scores (insufficient data).")
                    else:
                        # Show TMV scores in a nice table
                        expl = pd.DataFrame(
                            {
                                "Metric": list(scores.keys()),
                                "Value": list(scores.values()),
                            }
                        )
                        st.table(expl)
            except Exception as e:
                st.error(f"Failed to compute TMV indicators for {sel}: {e}")

        with col_right:
            st.markdown("#### Notes")
            st.write(
                """
                - **Trend Score**: EMA + Supertrend alignment  
                - **Momentum Score**: MACD, RSI, ADX  
                - **Volume Score**: OBV & MFI behaviour  
                - **TMV Score**: Weighted combination of the three  
                - **Reversal Probability**: Based on RSI extremes over recent candles  
                """
            )


# -----------------------------
# Footer / shareable link helper
# -----------------------------

st.markdown("---")
st.caption("Powered by Zerodha KiteConnect, Google Sheets, and your TMV engine.")
