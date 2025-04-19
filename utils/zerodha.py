import json
import os
import pandas as pd
from kiteconnect import KiteConnect
from datetime import datetime
from typing import Optional

# Path to token file (can be moved to env variable or Streamlit secret)
TOKEN_FILE = "zerodhatokensaver-1b53153ffd25.json"

def authenticate_kite() -> Optional[KiteConnect]:
    """
    Authenticates and returns a KiteConnect object using saved credentials.
    Returns None if credentials are invalid or missing.
    """
    try:
        with open(TOKEN_FILE, "r") as f:
            creds = json.load(f)
        
        kite = KiteConnect(api_key=creds["api_key"])
        kite.set_access_token(creds["access_token"])
        # This will raise exception if token is invalid
        kite.profile()
        return kite
    except Exception as e:
        print(f"[❌] Kite authentication failed: {e}")
        return None

def fetch_ohlcv_data(kite: KiteConnect, symbol: str, start: datetime, end: datetime, interval: str) -> pd.DataFrame:
    """
    Fetches OHLCV data for a given stock from Zerodha for the specified period and interval.
    Returns a cleaned DataFrame with datetime index.
    """
    try:
        # Mapping to exchange-specific symbols
        exchange_token_map = {
            "NSE": symbol
        }

        instrument = exchange_token_map.get("NSE")
        if not instrument:
            raise ValueError(f"Instrument token not found for {symbol}")

        data = kite.historical_data(
            instrument_token=kite.ltp(f"NSE:{symbol}")["NSE:" + symbol]["instrument_token"],
            from_date=start,
            to_date=end,
            interval=interval,
            continuous=False
        )

        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df.set_index("date", inplace=True)
        df.index = pd.to_datetime(df.index)
        return df

    except Exception as e:
        print(f"[⚠️] Failed to fetch OHLCV data for {symbol}: {e}")
        return pd.DataFrame()
