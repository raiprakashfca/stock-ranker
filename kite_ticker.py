
import os
import json
import time
import logging
import pandas as pd
from kiteconnect import KiteConnect, KiteTicker
import gspread
from oauth2client.service_account import ServiceAccountCredentials

logging.basicConfig(level=logging.INFO)

# Load Google Sheets credentials from environment variable
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(os.environ["GSPREAD_CREDENTIALS_JSON"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Read API keys from Google Sheet
sheet = client.open("ZerodhaTokenStore").sheet1
api_key, api_secret, access_token = sheet.row_values(1)[:3]

# Initialize Kite
kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# Fetch instruments and filter top stocks
nse_instruments = kite.instruments("NSE")
watchlist = ["RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "LT", "SBIN", "AXISBANK", "ITC", "KOTAKBANK", "DIVISLAB"]

token_map = {inst["tradingsymbol"]: inst["instrument_token"] for inst in nse_instruments if inst["tradingsymbol"] in watchlist}

# Initialize KiteTicker
kws = KiteTicker(api_key, access_token)

def on_ticks(ws, ticks):
    logging.info(f"✅ Received {len(ticks)} ticks")
    rows = []
    for tick in ticks:
        for symbol, token in token_map.items():
            if tick["instrument_token"] == token:
                ltp = tick.get("last_price", 0)
                rows.append([symbol, ltp])
    if rows:
        try:
            sheet = client.open("LiveLTPStore").sheet1
            sheet.update(values=[["Symbol", "LTP"]], range_name="A1:B1")
            sheet.update(values=rows, range_name="A2")
            logging.info("✅ LTPs updated to Google Sheet.")
        except Exception as e:
            logging.error(f"❌ Failed to update Google Sheet: {e}")

def on_connect(ws, response):
    logging.info("🔗 Connected to WebSocket.")
    ws.subscribe(list(token_map.values()))

def on_close(ws, code, reason):
    logging.warning(f"⚠️ Connection closed: {reason}")

def on_error(ws, code, reason):
    logging.error(f"❌ WebSocket error: {reason}")

if __name__ == "__main__":
    logging.info("🚀 Starting Kite Ticker WebSocket...")
    kws.on_ticks = on_ticks
    kws.on_connect = on_connect
    kws.on_close = on_close
    kws.on_error = on_error
    try:
        kws.connect(threaded=False)
    except Exception as e:
        logging.error(f"💥 Fatal error: {e}")
