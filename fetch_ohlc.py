import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
from functools import lru_cache

from kiteconnect import KiteConnect

# We reuse your sheet-based creds loader so we don't touch st.secrets here.
from utils.token_utils import load_credentials_from_gsheet

IST = pytz.timezone("Asia/Kolkata")

# -------------------------------
# Kite helpers
# -------------------------------
@lru_cache(maxsize=1)
def _kite() -> KiteConnect:
    api_key, api_secret, access_token = load_credentials_from_gsheet()
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite

@lru_cache(maxsize=1)
def _nse_instruments_df() -> pd.DataFrame:
    k = _kite()
    inst = k.instruments(exchange="NSE")
    return pd.DataFrame(inst)

@lru_cache(maxsize=512)
def _instrument_token_for_symbol(symbol: str) -> int:
    """
    Resolve NSE instrument_token for a given trading symbol.
    Symbols in your app are like 'RELIANCE' or 'HDFCBANK'.
    """
    sym = symbol.replace("-", "_").upper().strip()
    df = _nse_instruments_df()
    hit = df[df["tradingsymbol"].str.upper() == sym]
    if hit.empty:
        # Try a looser match (sometimes symbols include series)
        hit = df[df["tradingsymbol"].str.upper().str.startswith(sym)]
    if hit.empty:
        raise ValueError(f"Could not resolve instrument_token for NSE:{symbol}")
    return int(hit.iloc[0]["instrument_token"])

# -------------------------------
# Public API
# -------------------------------
def fetch_ohlc_data(symbol: str, interval: str = "15minute", days: int = 7) -> pd.DataFrame:
    """
    Fetch OHLC dataframe for `symbol` from Kite historical API.
    interval: one of ['minute','3minute','5minute','10minute','15minute','30minute','60minute','day']
    days: lookback window (IST)
    Returns columns: ['date','open','high','low','close','volume'] (indexed by datetime)
    """
    k = _kite()
    token = _instrument_token_for_symbol(symbol)
    to_dt = datetime.now(IST)
    from_dt = to_dt - timedelta(days=max(1, int(days)))

    data = k.historical_data(
        instrument_token=token,
        from_date=from_dt,
        to_date=to_dt,
        interval=interval,
        continuous=False,
        oi=False,
    )
    if not data:
        raise RuntimeError(f"No historical data returned for {symbol} ({interval}, {days}d).")

    df = pd.DataFrame(data)
    # Normalize columns
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        df.sort_index(inplace=True)

    # Ensure expected columns exist
    for c in ["open", "high", "low", "close", "volume"]:
        if c not in df.columns:
            df[c] = np.nan

    return df[["open", "high", "low", "close", "volume"]]


def calculate_indicators(df: pd.DataFrame) -> dict:
    """
    Compute a compact set of indicators using `ta` library (no pandas_ta dependency).
    Returns a dict of latest values for display.
    """
    if df is None or df.empty:
        return {"error": "Empty OHLC dataframe"}

    # Guard against too-short frames
    if len(df) < 50:
        return {"warning": f"Not enough candles ({len(df)}) to compute indicators reliably."}

    import ta  # lightweight, already in your requirements

    out = {}

    close = df["close"]
    high = df["high"]
    low = df["low"]

    # --- Momentum: RSI
    rsi = ta.momentum.RSIIndicator(close=close, window=14).rsi()
    out["RSI(14)"] = float(round(rsi.iloc[-1], 2))

    # --- Trend: EMAs and slope
    ema8 = ta.trend.EMAIndicator(close=close, window=8).ema_indicator()
    ema21 = ta.trend.EMAIndicator(close=close, window=21).ema_indicator()
    out["EMA8"] = float(round(ema8.iloc[-1], 2))
    out["EMA21"] = float(round(ema21.iloc[-1], 2))
    out["Trend(EMA8>EMA21)"] = bool(ema8.iloc[-1] > ema21.iloc[-1])

    # --- MACD
    macd = ta.trend.MACD(close=close)
    out["MACD"] = float(round(macd.macd().iloc[-1], 4))
    out["MACD_signal"] = float(round(macd.macd_signal().iloc[-1], 4))
    out["MACD_hist"] = float(round(macd.macd_diff().iloc[-1], 4))

    # --- ADX (trend strength)
    adx = ta.trend.ADXIndicator(high=high, low=low, close=close, window=14)
    out["ADX(14)"] = float(round(adx.adx().iloc[-1], 2))

    # --- Volatility: ATR
    atr = ta.volatility.AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range()
    out["ATR(14)"] = float(round(atr.iloc[-1], 2))

    # --- Simple price context
    out["Close"] = float(round(close.iloc[-1], 2))
    out["DayChange% (close vs prev)"] = float(round((close.iloc[-1]/close.iloc[-2] - 1) * 100.0, 2))

    return out
