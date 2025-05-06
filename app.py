import streamlit as st
import pandas as pd
import numpy as np
import math
import time
from datetime import datetime, timedelta
from kiteconnect import KiteConnect
from utils.token_utils import load_credentials_from_gsheet
from streamlit_autorefresh import st_autorefresh

# ----------- Kite API Setup -----------
api_key, api_secret, access_token = load_credentials_from_gsheet()
kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# ----------- Helper Functions -----------

def get_ltp(symbols: list) -> pd.DataFrame:
    """
    Fetches the last traded price for a list of symbols.
    """
    try:
        raw = kite.ltp(symbols)
        records = []
        for sym, info in raw.items():
            records.append({"Symbol": sym, "LTP": info.get("last_price", None)})
        df = pd.DataFrame(records)
        df.set_index("Symbol", inplace=True)
        return df
    except Exception as e:
        st.error(f"Error fetching LTP: {e}")
        return pd.DataFrame(columns=["Symbol","LTP"])  


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def norm_cdf(x: float) -> float:
    return (1 + math.erf(x / math.sqrt(2))) / 2


def bs_greeks(option_type: str, S: float, K: float, T: float, r: float, sigma: float):
    """
    Calculates Black-Scholes Greeks for a European option.
    option_type: 'CE' for call, 'PE' for put
    S: spot price, K: strike, T: time to expiry in years
    r: risk-free rate (annual), sigma: volatility (annual decimal)
    Returns: delta, gamma, vega, theta
    """
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if option_type.upper() == "CE":
        delta = norm_cdf(d1)
        theta = (-(S * norm_pdf(d1) * sigma) / (2 * math.sqrt(T))
                 - r * K * math.exp(-r * T) * norm_cdf(d2)) / 365
    else:
        delta = norm_cdf(d1) - 1
        theta = (-(S * norm_pdf(d1) * sigma) / (2 * math.sqrt(T))
                 + r * K * math.exp(-r * T) * norm_cdf(-d2)) / 365
    gamma = norm_pdf(d1) / (S * sigma * math.sqrt(T))
    vega = S * norm_pdf(d1) * math.sqrt(T) / 100
    return delta, gamma, vega, theta

# ----------- Streamlit App -----------
st.set_page_config(page_title="📊 Market Insights", layout="wide")
st.title("📊 Market Insights Dashboard")

# Create tabs for modular UI
tabs = st.tabs(["Live LTP Dashboard", "Option Greeks Tracker"])

# ----- Tab 1: Live LTP Dashboard -----
with tabs[0]:
    st.header("🔄 Live LTP Dashboard")
    symbols_input = st.text_input(
        "Enter symbols (comma-separated, e.g., NSE:NIFTY 50, NSE:BANKNIFTY, NSE:RELIANCE)",
        value="NSE:NIFTY 50, NSE:BANKNIFTY"
    )
    refresh_sec = st.number_input("Refresh interval (seconds)", min_value=1, max_value=60, value=5)

    # Auto-refresh
    st_autorefresh(interval=refresh_sec * 1000, key="auto_ltp")

    # Prepare symbol list
    symbols = [s.strip() for s in symbols_input.split(",") if s.strip()]
    if symbols:
        df_ltp = get_ltp(symbols)
        if not df_ltp.empty:
            df_ltp["% Change"] = df_ltp["LTP"].pct_change() * 100
            st.dataframe(df_ltp.style.format({"LTP": "{:.2f}", "% Change": "{:.2f}%"}))
        else:
            st.warning("No LTP data to display.")
    else:
        st.info("Please enter at least one symbol.")

# ----- Tab 2: Option Greeks Tracker -----
with tabs[1]:
    st.header("📐 Option Greeks Tracker")
    col1, col2 = st.columns(2)
    with col1:
        underlying = st.text_input("Underlying symbol (e.g., NSE:NIFTY 50)", value="NSE:NIFTY 50")
        expiry = st.date_input("Expiry date", value=datetime.today() + timedelta(days=7))
        strikes_input = st.text_input("Strike prices (comma-separated)", value="17500,17600")
    with col2:
        sigma = st.number_input("Implied Volatility (decimal)", min_value=0.01, max_value=2.0, value=0.15)
        r = st.number_input("Risk-free rate (annual decimal)", min_value=0.0, max_value=0.2, value=0.06)

    if st.button("Calculate Greeks"):
        try:
            # Fetch spot price
            data = kite.ltp([underlying])
            S = data[underlying]["last_price"]
            T = (expiry - datetime.today()).days / 365
            greeks_records = []
            for K in [int(s) for s in strikes_input.split(",") if s.strip().isdigit()]:
                for opt_type in ["CE", "PE"]:
                    delta, gamma, vega, theta = bs_greeks(opt_type, S, K, T, r, sigma)
                    greeks_records.append({
                        "Strike": K,
                        "Type": opt_type,
                        "Delta": round(delta, 4),
                        "Gamma": round(gamma, 4),
                        "Vega": round(vega, 4),
                        "Theta": round(theta, 4)
                    })
            df_greeks = pd.DataFrame(greeks_records)
            st.dataframe(df_greeks.set_index(["Strike","Type"]))
        except Exception as e:
            st.error(f"Error calculating Greeks: {e}")

# ----------- End of app.py -----------

# Note: To enhance your Trend-Momentum-Volume (TMV) analysis, consider integrating institutional-grade indicators such as VWAP, ADX, and On-Balance Volume (OBV), and using higher-frequency data feeds.
