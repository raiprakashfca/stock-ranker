from kiteconnect import KiteTicker, KiteConnect
import json
import time
import os

# Load secrets from gspread secrets JSON or from .env
from oauth2client.service_account import ServiceAccountCredentials
import gspread

# Step 1: Load Zerodha API credentials from Google Sheet
def get_tokens_from_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(os.environ["GSPREAD_SERVICE_ACCOUNT"])  # Inject from secrets if running locally
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open("ZerodhaTokenStore").sheet1
    tokens = sheet.get_all_values()[0]
    return tokens[0], tokens[2]  # api_key, access_token

# Step 2: List of instrument tokens (You can automate this too)
SYMBOLS = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC", "AXISBANK",
    "LT", "KOTAKBANK", "BAJFINANCE", "ASIANPAINT", "WIPRO", "SUNPHARMA", "ULTRACEMCO"
]

def get_instrument_tokens(kite):
    instruments = kite.instruments("NSE")
    symbol_map = {i["tradingsymbol"]: i["instrument_token"] for i in instruments}
    return [symbol_map[symbol] for symbol in SYMBOLS if symbol in symbol_map]

# Step 3: WebSocket callbacks
def on_ticks(ws, ticks):
    print("✅ Live Ticks:")
    for tick in ticks:
        print(f"  🔹 {tick['instrument_token']} → ₹{tick['last_price']}")

def on_connect(ws, response):
    print("✅ WebSocket connected.")
    ws.subscribe(live_tokens)
    ws.set_mode(ws.MODE_LTP, live_tokens)

def on_close(ws, code, reason):
    print("❌ WebSocket closed:", code, reason)

if __name__ == "__main__":
    api_key, access_token = get_tokens_from_sheet()

    # Init Kite & fetch tokens
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    live_tokens = get_instrument_tokens(kite)

    kws = KiteTicker(api_key, access_token)
    kws.on_ticks = on_ticks
    kws.on_connect = on_connect
    kws.on_close = on_close

    kws.connect(threaded=True)

    while True:
        time.sleep(5)
