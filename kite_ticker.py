
import json
import os
import time
import logging
import gspread
from kiteconnect import KiteConnect, KiteTicker
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime

logging.basicConfig(level=logging.INFO)

# Decode credentials from environment variable
creds_dict = json.loads(os.environ["GSPREAD_CREDENTIALS_JSON"])

# Authorize gspread
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Read tokens from ZerodhaTokenStore
sheet = client.open("ZerodhaTokenStore").sheet1
api_key, api_secret, access_token = sheet.get_all_values()[0][:3]

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# Get instrument tokens from symbols in BackgroundAnalysisStore
try:
    sheet_symbols = client.open("BackgroundAnalysisStore").sheet1
    symbols = [row[0] for row in sheet_symbols.get_all_values()[1:] if row]
    instruments = kite.ltp(symbols)
    tokens = [instruments[sym]["instrument_token"] for sym in instruments]
except Exception as e:
    logging.error(f"Failed to fetch instrument tokens: {e}")
    tokens = []

# WebSocket setup
ticker = KiteTicker(api_key, access_token)

ltp_data = {}

def on_ticks(ws, ticks):
    global ltp_data
    for tick in ticks:
        token = tick["instrument_token"]
        ltp = tick.get("last_price")
        for sym, meta in instruments.items():
            if meta["instrument_token"] == token:
                ltp_data[sym] = ltp
    logging.info("✅ LTPs updated.")

def on_connect(ws, response):
    ws.subscribe(tokens)
    logging.info("🎯 Subscribed to tokens.")

def on_close(ws, code, reason):
    logging.warning(f"⚠️ Connection closed: {reason}")

def on_error(ws, code, reason):
    logging.error(f"❌ WebSocket error: {reason}")

ticker.on_ticks = on_ticks
ticker.on_connect = on_connect
ticker.on_close = on_close
ticker.on_error = on_error

logging.info("🚀 Starting Kite Ticker WebSocket...")
ticker.connect(threaded=True)

# Periodically update LiveLTPStore
while True:
    if ltp_data:
        try:
            sheet_ltp = client.open("LiveLTPStore").sheet1
            rows = [[sym, ltp] for sym, ltp in ltp_data.items()]
            sheet_ltp.update("A1:B1", [["Symbol", "LTP"]])
            sheet_ltp.update("A2", rows)
            logging.info("📈 Live LTPs pushed to sheet.")
        except Exception as e:
            logging.error(f"❌ Failed to update LTP sheet: {e}")
    time.sleep(60)
