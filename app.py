# app.py

import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
import pytz

from utils.token_panel import render_token_panel
from utils.google_client import get_gspread_client
from utils.tmv_explainer import render_tmv_explainer
from utils.indicators import compute_indicator_details
from utils.ltp import add_live_ltp


IST = pytz.timezone("Asia/Kolkata")
MAX_STALENESS_MIN = 20                     # HARD STOP if older than 20 minutes
WORKBOOK = "BackgroundAnalysisStore"
LIVESCORES_SHEET = "LiveScores"


# ----------------------------------------------------------
#  Fetch TMV from Google Sheets (authoritative source)
# ----------------------------------------------------------
@st.cache_data(ttl=5)
def fetch_live_scores():
    client = get_gspread_client()
    ws = client.open(WORKBOOK).worksheet(LIVESCORES_SHEET)
    values = ws.get_all_values()

    df = pd.DataFrame(values[1:], columns=values[0])
    return df


# ----------------------------------------------------------
#  Freshness Parser
# ----------------------------------------------------------
def parse_asof(df: pd.DataFrame):
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


# ----------------------------------------------------------
#  Freshness Badge
# ----------------------------------------------------------
def compute_freshness_badge(as_of: datetime):
    now = datetime.now(IST)
    age_min = (now - as_of).total_seconds() / 60

    if age_min < 5:
        return ("🟢 LIVE", "green")
    elif age_min < MAX_STALENESS_MIN:
        return ("🟡 LATE", "orange")
    else:
        return ("🔴 STALE", "red")


# ----------------------------------------------------------
#  UI Header
# ----------------------------------------------------------
def render_header(as_of):
    st.title("📊 TMV Stock Ranker")

    if as_of is None:
        st.error("❌ Missing AsOf timestamp — data freshness unknown.")
        st.stop()

    badge_text, badge_color = compute_freshness_badge(as_of)

    st.markdown(
        f"""
        <div style='padding:8px;border-radius:8px;
                    background:#f2f2f2;display:inline-block;'>
            <strong style='color:{badge_color};'>{badge_text}</strong>
            <span style='margin-left:10px;color:#555;'>
                Updated: {as_of.strftime("%Y-%m-%d %H:%M:%S")} IST
            </span>
        </div>
        """,
        unsafe_allow_html=True
    )


# ----------------------------------------------------------
#  MAIN
# ----------------------------------------------------------
def main():
    st.sidebar.header("🔐 Zerodha Token")
    render_token_panel()

    df = fetch_live_scores()

    # ----- Freshness enforcement -----
    as_of = parse_asof(df)

    if as_of is None:
        st.error("🛑 LiveScores contains NO valid AsOf timestamps — refusing to load stale data.")
        st.stop()

    now = datetime.now(IST)
    age_min = (now - as_of).total_seconds() / 60

    if age_min > MAX_STALENESS_MIN:
        st.error(
            f"🛑 LiveScores is {age_min:.1f} minutes old — "
            f"maximum allowed is {MAX_STALENESS_MIN} minutes.\n\n"
            "Data is stale — refusing to load for safety."
        )
        st.stop()

    render_header(as_of)

    # Convert numeric columns if any
    numeric_cols = ["TMV Score", "Trend Score", "Momentum Score", "Volume Score"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Add LTP & %Change
    df = add_live_ltp(df)

    st.dataframe(df, use_container_width=True)

    # --- Indicator Explainer Expanders ---
    for _, row in df.iterrows():
        with st.expander(f"{row['Symbol']} — TMV Details"):
            details = compute_indicator_details(row["Symbol"])
            render_tmv_explainer(details)


if __name__ == "__main__":
    main()
