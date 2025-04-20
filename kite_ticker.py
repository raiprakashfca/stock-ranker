from kiteconnect import KiteTicker, KiteConnect
import json
import time
import os
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from io import BytesIO

# Load Zerodha API credentials from the environment
def get_tokens_from_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(os.environ["GSPREAD_SERVICE_ACCOUNT"])  # Inject from secrets if running locally
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open("ZerodhaTokenStore").sheet1
    tokens = sheet.get_all_values()[0]
    return tokens[0], tokens[2]  # api_key, access_token

# List of NIFTY 50 instrument tokens
SYMBOLS = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC", "AXISBANK",
    "LT", "KOTAKBANK", "BAJFINANCE", "ASIANPAINT", "WIPRO", "SUNPHARMA", "ULTRACEMCO"
]

def get_instrument_tokens(kite):
    instruments = kite.instruments("NSE")
    symbol_map = {i["tradingsymbol"]: i["instrument_token"] for i in instruments}
    return [symbol_map[symbol] for symbol in SYMBOLS if symbol in symbol_map]

# WebSocket callbacks
def on_ticks(ws, ticks):
    print("✅ Live Ticks:")
    ltp_data = []
    for tick in ticks:
        symbol = tick['instrument_token']
        ltp = tick['last_price']
        print(f"  🔹 {symbol} → ₹{ltp}")
        ltp_data.append({"Symbol": symbol, "LTP": ltp})
    
    if ltp_data:
        update_google_sheet(ltp_data)

def on_connect(ws, response):
    print("✅ WebSocket connected.")
    ws.subscribe(live_tokens)
    ws.set_mode(ws.MODE_LTP, live_tokens)

def on_close(ws, code, reason):
    print(f"❌ WebSocket closed: {code}, {reason}")

# Function to update Google Sheets with LTP data
def update_google_sheet(ltp_data):
    try:
        # Fetch credentials
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(os.environ["GSPREAD_SERVICE_ACCOUNT"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # Open the sheet and select the "LiveLTPs" tab
        sheet = client.open("Stock Rankings").worksheet("LiveLTPs")

        # Insert the data into the sheet
        for ltp in ltp_data:
            sheet.append_row([ltp['Symbol'], ltp['LTP']])
        print("✅ Live data updated to Google Sheet.")
    except Exception as e:
        print(f"⚠️ Failed to update Google Sheet: {e}")

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

    # Connect to WebSocket (live)
    kws.connect(threaded=True)

    while True:
        time.sleep(5)
