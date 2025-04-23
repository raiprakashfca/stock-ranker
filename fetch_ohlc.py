import streamlit as st
import pandas as pd
from kiteconnect import KiteConnect
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
import gspread
import pandas_ta as ta

def get_kite_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scope
    )
    client = gspread.authorize(credentials)
    sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")
    api_key = sheet.acell("A1").value
    access_token = sheet.acell("C1").value

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite

@st.cache_data(ttl=600)
def fetch_ohlc_data(symbol: str, interval: str, duration_days: int):
    kite = get_kite_client()
    instrument_token = kite.ltp([f"NSE:{symbol}"])[f"NSE:{symbol}"]["instrument_token"]

    # Extended window to improve indicator reliability
    if interval == "15minute":
        duration_days = 7
    elif interval == "day":
        duration_days = 90

    end_date = datetime.now()
    start_date = end_date - timedelta(days=duration_days)

    ohlc = kite.historical_data(instrument_token, start_date, end_date, interval)
    df = pd.DataFrame(ohlc)
    df.set_index("date", inplace=True)
    return df

def calculate_indicators(df):
    try:
        macd = df.ta.macd()
        adx = df.ta.adx()
        return {
            "EMA_8": df.ta.ema(length=8).iloc[-1],
            "EMA_21": df.ta.ema(length=21).iloc[-1],
            "RSI": df.ta.rsi(length=14).iloc[-1],
            "MACD": macd["MACD_12_26_9"].iloc[-1] if "MACD_12_26_9" in macd.columns else None,
            "ADX": adx["ADX_14"].iloc[-1] if "ADX_14" in adx.columns else None,
            "OBV": df.ta.obv().iloc[-1],
            "MFI": df.ta.mfi().iloc[-1]
        }
    except Exception as e:
        return {"Error": str(e)}
