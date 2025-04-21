import time
import json
import gspread
from kiteconnect import KiteConnect
from oauth2client.service_account import ServiceAccountCredentials

# Setup: Google Sheets Credentials
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
with open("zerodhatokensaver-1b53153ffd25.json") as f:
    creds_dict = json.load(f)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Setup: Zerodha Tokens
token_sheet = client.open("ZerodhaTokenStore").sheet1
tokens = token_sheet.get_all_values()[0]
kite = KiteConnect(api_key=tokens[0])
kite.set_access_token(tokens[2])

# Stocks to monitor (NIFTY 50)
symbols = [
    "RELIANCE", "INFY", "TCS", "ICICIBANK", "HDFCBANK", "SBIN", "BHARTIARTL", "LT",
    "AXISBANK", "KOTAKBANK", "ITC", "ASIANPAINT", "HCLTECH", "WIPRO", "TECHM", "SUNPHARMA",
    "DIVISLAB", "DRREDDY", "TITAN", "NESTLEIND", "ULTRACEMCO", "TATASTEEL", "JSWSTEEL",
    "COALINDIA", "ONGC", "HINDALCO", "GRASIM", "UPL", "POWERGRID", "NTPC", "BPCL", "IOC",
    "INDUSINDBK", "HDFCLIFE", "SBILIFE", "APOLLOHOSP", "ADANIPORTS", "ADANIENT",
    "HEROMOTOCO", "BAJAJ-AUTO", "EICHERMOT", "M&M", "MARUTI", "BRITANNIA", "CIPLA",
    "TATACONSUM"
]

# Utility: Get instrument tokens
nse_instruments = kite.instruments("NSE")
symbol_map = {}
for inst in nse_instruments:
    if inst["tradingsymbol"] in symbols and inst["segment"] == "NSE":
        symbol_map[inst["tradingsymbol"]] = inst["instrument_token"]

# Loop to fetch and log
while True:
    try:
        quote_data = kite.ltp([f"NSE:{s}" for s in symbols])
        data = []
        for s in symbols:
            ltp = quote_data[f"NSE:{s}"]["last_price"]
            prev_close = quote_data[f"NSE:{s}"]["ohlc"]["close"]
            pct_change = round(((ltp - prev_close) / prev_close) * 100, 2)
            data.append([s, round(ltp, 2), pct_change])

        # Push to Sheet
        sheet = client.open("LiveLTPStore").sheet1
        sheet.clear()
        sheet.append_row(["Symbol", "LTP", "% Change"])
        sheet.append_rows(data)

        print("✅ LTP Data logged.")
        time.sleep(60)

    except Exception as e:
        print("❌ Error:", e)
        time.sleep(60)
