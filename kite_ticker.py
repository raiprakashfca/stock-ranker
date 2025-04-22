
import os
import json
import time
import logging
import pandas as pd
from kiteconnect import KiteConnect, KiteTicker
import gspread
from oauth2client.service_account import ServiceAccountCredentials

logging.basicConfig(level=logging.INFO)

# Load credentials from environment variable
creds_dict = json.loads(os.environ["GSPREAD_CREDENTIALS_JSON"])
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Zerodha credentials from Google Sheet
token_sheet = client.open("ZerodhaTokenStore").sheet1
tokens = token_sheet.get_all_values()[0][:3]
api_key, api_secret, access_token = tokens

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)
kws = KiteTicker(api_key, access_token)

# Read instruments from Google Sheet
sheet = client.open("LiveLTPStore").sheet1
df = pd.DataFrame(sheet.get_all_records())

instrument_tokens = []
symbol_map = {}

all_instruments = pd.DataFrame(kite.instruments("NSE"))

for symbol in df["Symbol"]:
    match = all_instruments[all_instruments["tradingsymbol"] == symbol]
    if not match.empty:
        token = int(match.iloc[0]["instrument_token"])
        instrument_tokens.append(token)
        symbol_map[token] = symbol
    else:
        logging.warning(f"⚠️ Instrument not found for {symbol}")

prices = {}

def on_ticks(ws, ticks):
    for tick in ticks:
        token = tick["instrument_token"]
        last_price = tick["last_price"]
        symbol = symbol_map.get(token)
        if symbol:
            prices[symbol] = last_price
    update_sheet()

def update_sheet():
    current_data = sheet.get_all_records()
    updated_rows = []
    for row in current_data:
        symbol = row["Symbol"]
        old_price = row["LTP"]
        new_price = prices.get(symbol, old_price)
        change = ((new_price - old_price) / old_price) * 100 if old_price else 0
        updated_rows.append([symbol, round(new_price, 2), f"{change:.2f}%"])

    sheet.update("A1:C1", [["Symbol", "LTP", "% Change"]])
    sheet.update("A2", updated_rows)
    logging.info("✅ Sheet updated")

def on_connect(ws, response):
    logging.info("✅ WebSocket connected")
    ws.subscribe(instrument_tokens)

def on_close(ws, code, reason):
    logging.warning(f"⚠️ Connection closed: {reason}")

def on_error(ws, code, reason):
    logging.error(f"❌ WebSocket error: {reason}")

kws.on_ticks = on_ticks
kws.on_connect = on_connect
kws.on_close = on_close
kws.on_error = on_error

logging.info("🚀 Starting Kite Ticker WebSocket...")
kws.connect(threaded=False)
