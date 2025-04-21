# utils/zerodha.py

from kiteconnect import KiteConnect
import pandas as pd
import datetime as dt

def get_kite(api_key, access_token):
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite

def get_stock_data(kite, symbol, interval, days):
    to_date = dt.datetime.now()
    from_date = to_date - dt.timedelta(days=days)

    try:
        instrument_token = kite.ltp(f"NSE:{symbol}")[f"NSE:{symbol}"]["instrument_token"]
        data = kite.historical_data(
            instrument_token,
            from_date,
            to_date,
            interval,
            continuous=False,
            oi=False
        )
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return pd.DataFrame()
