# utils/zerodha.py

from datetime import datetime, timedelta
import pandas as pd

# Map symbol to NSE instrument format
def format_symbol(symbol):
    return f"NSE:{symbol}"

# Determine from-date for given interval
def get_from_date(interval, days):
    if interval == "day":
        return datetime.now() - timedelta(days=days)
    elif interval == "60minute":
        return datetime.now() - timedelta(days=days)
    elif interval == "15minute":
        return datetime.now() - timedelta(days=days)
    else:
        raise ValueError(f"Unsupported interval: {interval}")

# Fetch historical OHLC data using Kite API
def get_stock_data(kite, symbol, interval, days=30):
    try:
        instruments = kite.instruments("NSE")
        token_row = next((item for item in instruments if item["tradingsymbol"] == symbol), None)
        if not token_row:
            raise ValueError(f"Instrument not found for {symbol}")
        instrument_token = token_row["instrument_token"]

        from_date = get_from_date(interval, days)
        to_date = datetime.now()

        ohlc = kite.historical_data(
            instrument_token,
            from_date,
            to_date,
            interval=interval,
            continuous=False,
            oi=True
        )
        return pd.DataFrame(ohlc)
    except Exception as e:
        print(f"❌ Error fetching data for {symbol}: {e}")
        return pd.DataFrame()
