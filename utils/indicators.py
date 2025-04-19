import pandas as pd
import numpy as np
import pandas_ta as ta

def calculate_scores(df):
    result = {}

    if len(df) < 50:
        return {
            "Trend Score": 0.0,
            "Momentum Score": 0.0,
            "Volume Score": 0.0,
            "TMV Score": 0.0,
            "Trend Direction": "Neutral",
            "Reversal Probability": 0.0
        }

    # Trend Indicators
    df["ema8"] = ta.ema(df["close"], length=8)
    df["ema21"] = ta.ema(df["close"], length=21)
    df["hull"] = ta.hma(df["close"], length=14)
    df["supertrend"] = ta.supertrend(df["high"], df["low"], df["close"])[f"SUPERT_7_3.0"]

    trend_score = 0
    if df["ema8"].iloc[-1] > df["ema21"].iloc[-1]:
        trend_score += 0.25
    if df["close"].iloc[-1] > df["hull"].iloc[-1]:
        trend_score += 0.25
    if df["close"].iloc[-1] > df["supertrend"].iloc[-1]:
        trend_score += 0.25
    if df["ema8"].iloc[-1] > df["close"].iloc[-1]:
        trend_score += 0.25

    # Momentum Indicators
    macd = ta.macd(df["close"])
    rsi = ta.rsi(df["close"])
    adx = ta.adx(df["high"], df["low"], df["close"])

    momentum_score = 0
    if macd["MACD_12_26_9"].iloc[-1] > macd["MACDs_12_26_9"].iloc[-1]:
        momentum_score += 0.33
    if rsi.iloc[-1] > 50:
        momentum_score += 0.33
    if adx["ADX_14"].iloc[-1] > 20:
        momentum_score += 0.34

    # Volume Indicators
    obv = ta.obv(df["close"], df["volume"])
    mfi = ta.mfi(df["high"], df["low"], df["close"], df["volume"])
    volume_score = 0
    if obv.iloc[-1] > obv.iloc[-5]:
        volume_score += 0.5
    if mfi.iloc[-1] > 50:
        volume_score += 0.5

    # Total Score
    tmv_score = round((trend_score + momentum_score + volume_score) / 3, 2)

    # Trend Direction
    if trend_score >= 0.75:
        direction = "Bullish"
    elif trend_score <= 0.25:
        direction = "Bearish"
    else:
        direction = "Neutral"

    # Reversal Probability
    reversal_probability = 0.0
    if rsi.iloc[-1] > 70 and trend_score <= 0.25:
        reversal_probability = 0.85
    elif rsi.iloc[-1] < 30 and trend_score >= 0.75:
        reversal_probability = 0.85
    elif rsi.iloc[-1] > 65 or rsi.iloc[-1] < 35:
        reversal_probability = 0.5
    else:
        reversal_probability = 0.2

    result["Trend Score"] = round(trend_score, 2)
    result["Momentum Score"] = round(momentum_score, 2)
    result["Volume Score"] = round(volume_score, 2)
    result["TMV Score"] = tmv_score
    result["Trend Direction"] = direction
    result["Reversal Probability"] = round(reversal_probability, 2)

    return result
