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

    end_date = datetime.now()
    start_date = end_date - timedelta(days=duration_days)

    ohlc = kite.historical_data(instrument_token, start_date, end_date, interval)
    df = pd.DataFrame(ohlc)
    df.set_index("date", inplace=True)
    return df

def calculate_indicators(df):
    return {
        "EMA_8": df.ta.ema(length=8).iloc[-1],
        "EMA_21": df.ta.ema(length=21).iloc[-1],
        "RSI": df.ta.rsi(length=14).iloc[-1],
        "MACD": df.ta.macd().iloc[-1]["MACD_12_26_9"],
        "ADX": df.ta.adx().iloc[-1]["ADX_14"],
        "OBV": df.ta.obv().iloc[-1],
        "MFI": df.ta.mfi().iloc[-1]
    }
