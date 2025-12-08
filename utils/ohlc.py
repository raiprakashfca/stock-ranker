# utils/ohlc.py

from datetime import datetime, timedelta
from typing import Literal

import pandas as pd

from .token_store import get_kite


def fetch_ohlc(
    symbol: str,
    interval: Literal["day", "60minute", "15minute"] = "day",
    days: int = 60,
) -> pd.DataFrame:
    """
    Fetch OHLC data for a symbol for the last `days` days.
    """
    kite = get_kite(validate=False)

    # Resolve instrument token via LTP lookup
    inst = kite.ltp([f"NSE:{symbol}"])
    if not inst:
        return pd.DataFrame()

    instrument_token = list(inst.values())[0]["instrument_token"]

    to_dt = datetime.now()
    from_dt = to_dt - timedelta(days=days)

    hist = kite.historical_data(
        instrument_token=instrument_token,
        from_date=from_dt,
        to_date=to_dt,
        interval=interval,
    )
    if not hist:
        return pd.DataFrame()

    df = pd.DataFrame(hist)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df
