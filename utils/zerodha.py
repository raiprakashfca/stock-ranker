import pandas as pd
import datetime
from kiteconnect import KiteConnect
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def get_kite():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("zerodhatokensaver-1b53153ffd25.json", scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_url("<YOUR_GOOGLE_SHEET_URL>")
    tokens = sheet.sheet1.row_values(1)
    api_key, api_secret, access_token = tokens[0], tokens[1], tokens[2]

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite

def get_instrument_token(kite, tradingsymbol):
    instruments = kite.instruments(exchange="NSE")
    for instrument in instruments:
        if instrument["tradingsymbol"] == tradingsymbol:
            return instrument["instrument_token"]
    raise ValueError(f"Instrument token not found for {tradingsymbol}")

def get_stock_data(kite, symbol, interval, days):
    token = get_instrument_token(kite, symbol)
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=days)
    data = kite.historical_data(token, start_date, end_date, interval)
    df = pd.DataFrame(data)
    df.set_index("date", inplace=True)
    return df
