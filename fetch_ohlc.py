import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
from datetime import datetime, timedelta
from kiteconnect import KiteConnect
from google.oauth2.service_account import Credentials
import gspread

# ----------- Kite Client Setup -----------
@st.cache_data(ttl=86400)
def get_kite_client():
    """
    Instantiate and return a KiteConnect client using credentials from Google Sheets.
    """
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scope
    )
    client = gspread.authorize(creds)
    sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")
    api_key = sheet.acell("A1").value
    access_token = sheet.acell("C1").value

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite

# ----------- Fetch Historical OHLC Data -----------
@st.cache_data(ttl=600)
def fetch_ohlc_data(symbol: str, interval: str, duration_days: int) -> pd.DataFrame:
    """
    Fetch historical OHLC data for a symbol over a specified lookback period.
    symbol: trading symbol without exchange prefix e.g. "NIFTY 50" or "BAJAJ_AUTO".
    interval: one of 'minute', '15minute', 'day'.
    duration_days: number of days back.
    Returns a DataFrame indexed by datetime with columns: open, high, low, close, volume.
    """
    kite = get_kite_client()
    # Resolve instrument token via ltp
    key = f"NSE:{symbol.replace('_','-')}"
    ltp_info = kite.ltp([key]).get(key, {})
    token = ltp_info.get("instrument_token")
    if not token:
        raise ValueError(f"Instrument token not found for {symbol}")

    # Adjust lookback for reliability
    if interval == "15minute":
        duration_days = max(duration_days, 7)
    elif interval == "day":
        duration_days = max(duration_days, 90)

    to_dt = datetime.now()
    from_dt = to_dt - timedelta(days=duration_days)
    raw = kite.historical_data(
        instrument_token=token,
        from_date=from_dt,
        to_date=to_dt,
        interval=interval
    )
    df = pd.DataFrame(raw)
    df.set_index('date', inplace=True)
    return df

# ----------- Calculate Advanced Indicators -----------
def calculate_indicators(df: pd.DataFrame) -> dict:
    """
    Calculate a suite of professional-grade indicators on OHLCV data:
      - EMA 8, EMA 21
      - RSI (14), MACD (12,26,9)
      - ADX (14)
      - ATR-based SuperTrend (7,3.0)
      - OBV
      - MFI (14)
      - Volume Profile: POC, Value Area Low/High (70% volume)
    Returns a dict of indicator_name: latest_value
    """
    if df.empty:
        return {}

    ohlc = df[['open', 'high', 'low', 'close', 'volume']].copy()
    close = ohlc['close']
    high = ohlc['high']
    low = ohlc['low']
    vol = ohlc['volume']

    ind = {}
    # Trend & Momentum
    ind['EMA_8']  = ta.ema(close, length=8).iloc[-1]
    ind['EMA_21'] = ta.ema(close, length=21).iloc[-1]
    ind['RSI_14'] = ta.rsi(close, length=14).iloc[-1]
    macd_df      = ta.macd(close, fast=12, slow=26, signal=9)
    ind['MACD']  = macd_df['MACD_12_26_9'].iloc[-1]

    # Trend Strength
    adx_df       = ta.adx(high, low, close, length=14)
    ind['ADX_14'] = adx_df['ADX_14'].iloc[-1]

    # SuperTrend
    st_df        = ta.supertrend(high, low, close, length=7, multiplier=3.0)
    ind['SuperTrend'] = st_df['SUPERT_7_3.0'].iloc[-1]

    # Volume Flow
    ind['OBV']   = ta.obv(close, vol).iloc[-1]
    ind['MFI_14']= ta.mfi(high, low, close, vol, length=14).iloc[-1]

    # Volume Profile
    prices = close.values
    vols   = vol.values
    # Define price bins
    bins = np.linspace(prices.min(), prices.max(), 20)
    hist, edges = np.histogram(prices, bins=bins, weights=vols)
    # Point of Control (POC)
    poc_idx = np.argmax(hist)
    ind['POC'] = (edges[poc_idx] + edges[poc_idx+1]) / 2
    # Value Area (70% volume)
    total = vols.sum()
    sorted_bins = np.argsort(hist)[::-1]
    cumul = 0
    va = []
    for idx in sorted_bins:
        if cumul < 0.7 * total:
            cumul += hist[idx]
            va.append(idx)
        else:
            break
    va_edges = []
    for idx in va:
        va_edges.extend([edges[idx], edges[idx+1]])
    if va_edges:
        ind['ValueAreaLow']  = min(va_edges)
        ind['ValueAreaHigh'] = max(va_edges)
    else:
        ind['ValueAreaLow'] = ind['ValueAreaHigh'] = None

    return ind
