# utils/indicators.py

import pandas as pd
import pandas_ta as ta


def calculate_scores(df: pd.DataFrame) -> dict:
    """
    Compute Trend, Momentum, Volume scores + TMV Score and Reversal Probability.

    Expects columns: date, open, high, low, close, volume
    """
    scores: dict = {}

    required = {"date", "open", "high", "low", "close", "volume"}
    if not required.issubset(df.columns):
        return {}

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    df.sort_index(inplace=True)

    if len(df) < 50:
        # Not enough candles for meaningful TMV
        return {}

    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]

    # --- Trend ---
    ema8 = ta.ema(close, length=8)
    ema21 = ta.ema(close, length=21)
    st_df = ta.supertrend(high, low, close, length=7, multiplier=3.0)
    supertrend = st_df["SUPERT_7_3.0"] if "SUPERT_7_3.0" in st_df.columns else st_df.iloc[:, 0]

    trend_score = 0
    try:
        if ema8.iloc[-1] > ema21.iloc[-1]:
            trend_score += 1
        if close.iloc[-1] > supertrend.iloc[-1]:
            trend_score += 1
    except Exception:
        # if indicators are NaN, treat as neutral
        pass

    # --- Momentum ---
    macd = ta.macd(close)
    rsi = ta.rsi(close)
    adx = ta.adx(high, low, close)

    momentum_score = 0
    try:
        if macd["MACD_12_26_9"].iloc[-1] > macd["MACDs_12_26_9"].iloc[-1]:
            momentum_score += 1
        if rsi.iloc[-1] > 50:
            momentum_score += 1
        if adx["ADX_14"].iloc[-1] > 20:
            momentum_score += 1
    except Exception:
        pass

    # --- Volume ---
    obv = ta.obv(close, vol)
    mfi = ta.mfi(high, low, close, vol)

    volume_score = 0
    try:
        if obv.diff().iloc[-1] > 0:
            volume_score += 1
        if mfi.iloc[-1] > 50:
            volume_score += 1
    except Exception:
        pass

    # --- Rule-based TMV ---
    tmv_score = 0.0
    if trend_score == 2:
        tmv_score += 0.4
    elif trend_score == 1:
        tmv_score += 0.2

    if momentum_score == 3:
        tmv_score += 0.35
    elif momentum_score == 2:
        tmv_score += 0.25

    if volume_score == 2:
        tmv_score += 0.25
    elif volume_score == 1:
        tmv_score += 0.15

    scores["Trend Score"] = trend_score / 2 if trend_score else 0
    scores["Momentum Score"] = momentum_score / 3 if momentum_score else 0
    scores["Volume Score"] = volume_score / 2 if volume_score else 0
    scores["TMV Score"] = round(tmv_score, 2)

    # Trend direction
    if trend_score == 2:
        scores["Trend Direction"] = "Bullish"
    elif trend_score == 0:
        scores["Trend Direction"] = "Bearish"
    else:
        scores["Trend Direction"] = "Neutral"

    # Reversal probability based on RSI extremes in last 5 candles
    try:
        recent_rsi = rsi.dropna().tail(5)
        if len(recent_rsi) == 0:
            scores["Reversal Probability"] = 0.0
        else:
            reversal = ((recent_rsi < 30) | (recent_rsi > 70)).sum() / len(recent_rsi)
            scores["Reversal Probability"] = round(float(reversal), 2)
    except Exception:
        scores["Reversal Probability"] = 0.0

    return scores
