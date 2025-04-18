import pandas as pd
import datetime
from kiteconnect import KiteConnect
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import streamlit as st

def get_kite():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["gspread_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1cjy-TxRw3V_hxKd1p87CKNIv-O7QUatDQ1WkKe2m3T0/edit#gid=2011235067")
    tokens = sheet.sheet1.row_values(1)
    api_key, api_secret, access_token = tokens[0], tokens[1], tokens[2]

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite

def get_instrument_token(kite, tradingsymbol):
    instruments = kite.instruments(exchange="NSE")
    for instrument in instruments:
        if instrument["tradingsymbol"] == tradingsymbol:
            return instrument["instrument_token"]
    raise ValueError(f"Instrument token not found for {tradingsymbol}")

def get_stock_data(kite, symbol, interval, days):
    token = get_instrument_token(kite, symbol)
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=days)
    data = kite.historical_data(token, start_date, end_date, interval)
    df = pd.DataFrame(data)
    df.set_index("date", inplace=True)
    return df
