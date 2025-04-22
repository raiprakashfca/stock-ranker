import os
import json
import time
import gspread
import pandas as pd
from kiteconnect import KiteConnect, KiteTicker
from oauth2client.service_account import ServiceAccountCredentials

# Load credentials from environment variable
creds_dict = json.loads(os.environ["GSPREAD_CREDENTIALS_JSON"])

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

sheet = client.open("LiveLTPStore").sheet1
sheet.update("A1:C1", [["Symbol", "LTP", "% Change"]])  # Ensure 3 headers

# Load symbols
symbols = [row[0] for row in sheet.get_all_values()[1:] if row[0]]

# Zerodha tokens
token_sheet = client.open("ZerodhaTokenStore").sheet1
tokens = token_sheet.get_all_values()[0]
api_key, api_secret, access_token = tokens[0], tokens[1], tokens[2]

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)
ltps = {}

# Get instrument tokens
instruments = kite.instruments()
symbol_token_map = {i["tradingsymbol"]: i["instrument_token"] for i in instruments if i["tradingsymbol"] in symbols}

tokens_to_subscribe = list(symbol_token_map.values())
rev_map = {v: k for k, v in symbol_token_map.items()}

# Store previous LTPs to calculate % change
prev_ltp = {}

def on_ticks(ws, ticks):
    global ltps
    for tick in ticks:
        symbol = rev_map.get(tick["instrument_token"])
        ltp = tick["last_price"]
        if symbol:
            old_ltp = prev_ltp.get(symbol, ltp)
            change = ((ltp - old_ltp) / old_ltp) * 100 if old_ltp else 0
            ltps[symbol] = (ltp, round(change, 2))
            prev_ltp[symbol] = ltp

def on_connect(ws, response):
    ws.subscribe(tokens_to_subscribe)

def on_close(ws, code, reason):
    print("WebSocket closed:", reason)

def write_to_sheet():
    rows = [[s, v[0], v[1]] for s, v in ltps.items()]
    if rows:
        sheet.update("A2", rows)

if __name__ == "__main__":
    print("🚀 Starting Kite Ticker WebSocket...")
    kws = KiteTicker(api_key, access_token)
    kws.on_ticks = on_ticks
    kws.on_connect = on_connect
    kws.on_close = on_close

    try:
        kws.connect(threaded=True)
        while True:
            time.sleep(60)
            write_to_sheet()
    except Exception as e:
        print("❌ WebSocket error:", e)
