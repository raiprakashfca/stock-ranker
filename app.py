import json
import time
from kiteconnect import KiteConnect, KiteTicker
import gspread
import pandas as pd
import streamlit as st
from oauth2client.service_account import ServiceAccountCredentials

# === CONFIGURATION ===
LTP_SHEET_NAME = "LiveLTPStore"
SYMBOLS = [
    "RELIANCE", "INFY", "TCS", "ICICIBANK", "HDFCBANK",
    "SBIN", "BHARTIARTL", "AXISBANK", "LT", "ITC",
    "KOTAKBANK", "HCLTECH", "WIPRO", "TECHM", "ADANIENT",
    "ADANIPORTS", "BAJAJFINSV", "BAJFINANCE", "TITAN", "POWERGRID",
    "COALINDIA", "NTPC", "JSWSTEEL", "ULTRACEMCO", "TATAMOTORS",
    "TATASTEEL", "BPCL", "ONGC", "DIVISLAB", "SUNPHARMA",
    "HINDALCO", "NESTLEIND", "ASIANPAINT", "CIPLA", "SBILIFE",
    "HDFCLIFE", "GRASIM", "HEROMOTOCO", "EICHERMOT", "BRITANNIA",
    "UPL", "APOLLOHOSP", "BAJAJ-AUTO", "INDUSINDBK", "DRREDDY",
    "MARUTI", "M&M", "HINDUNILVR", "TATACONSUM", "ICICIPRULI"
]

# === STEP 1: Load API and Sheet Credentials ===
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
with open("zerodhatokensaver-1b53153ffd25.json") as f:
    creds_dict = json.load(f)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open(LTP_SHEET_NAME).sheet1

tokens = client.open("ZerodhaTokenStore").sheet1.get_all_values()[0]
api_key, api_secret, access_token = tokens[0], tokens[1], tokens[2]

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# === STEP 2: Get Instrument Tokens for Desired Stocks ===
print("Fetching instrument tokens...")
instruments = kite.instruments("NSE")
symbol_map = {}
for item in instruments:
    if item["tradingsymbol"] in SYMBOLS and item["segment"] == "NSE":
        symbol_map[item["instrument_token"]] = item["tradingsymbol"]

print(f"Tracking {len(symbol_map)} symbols...")

# === STEP 3: Set up KiteTicker ===
kws = KiteTicker(api_key, access_token)

# === STEP 4: Live Tick Callback ===
def on_ticks(ws, ticks):
    data = []
    for tick in ticks:
        instrument_token = tick["instrument_token"]
        ltp = tick.get("last_price")
        symbol = symbol_map.get(instrument_token, "Unknown")
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        data.append([timestamp, symbol, ltp])

    if data:
        try:
            df = pd.DataFrame(data, columns=["Timestamp", "Symbol", "LTP"])
            sheet_data = sheet.get_all_records()
            existing = pd.DataFrame(sheet_data)
            merged = pd.concat([existing, df], ignore_index=True).drop_duplicates(subset=["Symbol"], keep="last")
            sheet.clear()
            sheet.append_rows([list(merged.columns)] + merged.astype(str).values.tolist())
            print(f"Logged {len(data)} LTPs at {timestamp}")
        except Exception as e:
            print(f"Error updating sheet: {e}")

def on_connect(ws, response):
    print("Connected to KiteTicker WebSocket!")
    ws.subscribe(list(symbol_map.keys()))

def on_close(ws, code, reason):
    print("WebSocket closed", code, reason)

def on_error(ws, code, reason):
    print("WebSocket error", code, reason)

kws.on_ticks = on_ticks
kws.on_connect = on_connect
kws.on_close = on_close
kws.on_error = on_error

print("Starting WebSocket stream...")
kws.connect(threaded=False)
