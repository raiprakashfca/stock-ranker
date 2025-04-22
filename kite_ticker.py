
import os
import json
import time
import logging
import pandas as pd
import numpy as np
import gspread
from kiteconnect import KiteConnect, KiteTicker
from oauth2client.service_account import ServiceAccountCredentials
import streamlit as st

logging.basicConfig(level=logging.INFO)

# Load credentials from Streamlit secrets
creds_dict = st.secrets["gspread_service_account"]

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Get API Key and Access Token
token_sheet = client.open("ZerodhaTokenStore").sheet1
api_key, api_secret, access_token = token_sheet.get_all_values()[0][:3]

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# Prepare the LTP sheet
sheet = client.open("LiveLTPStore").sheet1
sheet.update("A1:C1", [["Symbol", "LTP", "% Change"]])  # Update header

symbols = [row[0] for row in sheet.get_all_values()[1:] if row]
instrument_dump = kite.instruments("NSE")
symbol_token_map = {}
close_prices = {}

for symbol in symbols:
    try:
        token = next(i["instrument_token"] for i in instrument_dump if i["tradingsymbol"] == symbol and i["segment"] == "NSE")
        ltp_data = kite.ltp(f"NSE:{symbol}")
        close = ltp_data[f"NSE:{symbol}"]["ohlc"]["close"]
        symbol_token_map[symbol] = token
        close_prices[symbol] = close
    except:
        logging.warning(f"⚠️ Skipping {symbol}: Not found in instrument dump")

tokens = list(symbol_token_map.values())
kws = KiteTicker(api_key, access_token)

ltp_data = {}

def on_ticks(ws, ticks):
    global ltp_data
    for tick in ticks:
        for symbol, token in symbol_token_map.items():
            if tick["instrument_token"] == token:
                ltp = tick["last_price"]
                close = close_prices.get(symbol, ltp)
                pct = ((ltp - close) / close) * 100
                ltp_data[symbol] = (ltp, pct)

        if len(ltp_data) == len(symbol_token_map):
            rows = [[sym, f"{ltp_data[sym][0]:.2f}", f"{ltp_data[sym][1]:.2f}%"] for sym in symbol_token_map.keys()]
            try:
                sheet.update("A2", rows)
                logging.info("✅ Updated LiveLTPStore")
            except Exception as e:
                logging.error(f"❌ Failed to update sheet: {e}")

def on_connect(ws, response):
    ws.subscribe(tokens)

def on_close(ws, code, reason):
    logging.warning(f"⚠️ Connection closed: {reason}")

def on_error(ws, code, reason):
    logging.error(f"❌ WebSocket error: {reason}")

kws.on_ticks = on_ticks
kws.on_connect = on_connect
kws.on_close = on_close
kws.on_error = on_error

logging.info("🚀 Starting Kite Ticker WebSocket...")
kws.connect(threaded=True)

while True:
    time.sleep(60)
