
import os
import json
import base64
import time
import logging
import pandas as pd
from kiteconnect import KiteConnect, KiteTicker
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

# Decode and load Google Sheets credentials from environment variable
creds_base64 = os.environ.get("GSPREAD_CREDENTIALS_JSON", "")
if not creds_base64:
    raise ValueError("Missing GSPREAD_CREDENTIALS_JSON in environment variables")
creds_dict = json.loads(base64.b64decode(creds_base64).decode())

# Authorize gspread
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Read Zerodha API credentials and access token from Google Sheet
token_sheet = client.open("ZerodhaTokenStore").sheet1
tokens = token_sheet.get_all_values()[0]
api_key, api_secret, access_token = tokens[0], tokens[1], tokens[2]

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# Fetch instrument tokens for NIFTY 50 symbols
nifty50 = [s['tradingsymbol'] for s in kite.instruments("NSE") if s.get("name") == "NIFTY 50"]
tokens = {}
instrument_dump = kite.instruments("NSE")
for symbol in nifty50:
    try:
        instrument = next(i for i in instrument_dump if i["tradingsymbol"] == symbol)
        tokens[instrument["instrument_token"]] = symbol
    except StopIteration:
        logger.warning(f"Symbol not found: {symbol}")

# Prepare Google Sheet to store LTPs
sheet = client.open("LiveLTPStore").sheet1
sheet.update(values=[["Symbol", "LTP"]], range_name="A1:B1")

# Setup KiteTicker
kws = KiteTicker(api_key, access_token)

def on_ticks(ws, ticks):
    rows = []
    for tick in ticks:
        symbol = tokens.get(tick["instrument_token"], "")
        ltp = tick.get("last_price", 0)
        rows.append([symbol, ltp])
    if rows:
        try:
            sheet.update(values=rows, range_name="A2")
        except Exception as e:
            logger.error(f"❌ Failed to update sheet: {e}")
        else:
            logger.info("✅ Sheet updated with latest LTPs.")

def on_connect(ws, response):
    ws.subscribe(list(tokens.keys()))
    logger.info("✅ Subscribed to instrument tokens.")

def on_close(ws, code, reason):
    logger.warning(f"⚠️ Connection closed: {reason}")

def on_error(ws, code, reason):
    logger.error(f"❌ WebSocket error: {reason}")

logger.info("🚀 Starting Kite Ticker WebSocket...")
kws.on_ticks = on_ticks
kws.on_connect = on_connect
kws.on_close = on_close
kws.on_error = on_error

try:
    kws.connect(threaded=False)
except Exception as e:
    logger.error(f"❌ Failed to connect to WebSocket: {e}")
