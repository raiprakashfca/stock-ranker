import json
import os
import pandas as pd
import gspread
import logging
from kiteconnect import KiteConnect
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import streamlit as st

def get_kite(api_key, access_token):
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite

def get_stock_data(kite, symbol, interval, days):
    try:
        instrument = kite.ltp(f"NSE:{symbol}")
        if not instrument:
            return pd.DataFrame()
        instrument_token = list(instrument.values())[0]['instrument_token']

        from_date = datetime.now() - pd.Timedelta(days=days)
        to_date = datetime.now()

        historical_data = kite.historical_data(
            instrument_token=instrument_token,
            from_date=from_date,
            to_date=to_date,
            interval=interval
        )
        return pd.DataFrame(historical_data)
    except Exception as e:
        logging.warning(f"❌ Failed to fetch data for {symbol}: {e}")
        return pd.DataFrame()

def update_ltp_sheet():
    # Load credentials from secrets
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["gspread_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    # Read Zerodha token details from sheet
    token_sheet = client.open("ZerodhaTokenStore").sheet1
    tokens = token_sheet.get_all_values()[0]
    api_key, api_secret, access_token = tokens[0], tokens[1], tokens[2]

    # Initialize Kite
    kite = get_kite(api_key, access_token)

    # Read list of symbols from LiveLTPStore
    sheet = client.open("LiveLTPStore").sheet1
    symbols = [row[0] for row in sheet.get_all_values()[1:] if row]

    # Get live prices
    instruments = [f"NSE:{symbol}" for symbol in symbols]
    try:
        live_data = kite.ltp(instruments)
        rows = []
        for symbol in symbols:
            key = f"NSE:{symbol}"
            if key in live_data:
                ltp = live_data[key]['last_price']
                rows.append([symbol, ltp])
        # Update headers and data
        sheet.update(values=[["Symbol", "LTP"]], range_name="A1:B1")
        sheet.update(values=rows, range_name="A2")
    except Exception as e:
        logging.error(f"⚠️ Error updating LTPs: {e}")
