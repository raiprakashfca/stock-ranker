# utils/indicators.py

import pandas as pd
import numpy as np
import pandas_ta as ta

def calculate_scores(df):
    result = {}

    # =========================
    # TREND INDICATORS
    # =========================
    df["EMA_8"] = ta.ema(df["close"], length=8)
    df["EMA_21"] = ta.ema(df["close"], length=21)
    trend_ema = int(df["EMA_8"].iloc[-1] > df["EMA_21"].iloc[-1])

    alligator = ta.alligator(df["high"], df["low"], df["close"])
    trend_alligator = int(alligator["JAWl_13_8"].iloc[-1] < alligator["TEETHl_8_5"].iloc[-1] < alligator["LIPS_5_3"].iloc[-1])

    hull = ta.hma(df["close"], length=14)
    trend_hull = int(df["close"].iloc[-1] > hull.iloc[-1])

    supertrend = ta.supertrend(df["high"], df["low"], df["close"], period=10, multiplier=3.0)
    trend_st = int(supertrend["SUPERT_10_3.0"].iloc[-1] < df["close"].iloc[-1])

    trend_score = np.mean([trend_ema, trend_alligator, trend_hull, trend_st])
    result["Trend Score"] = round(trend_score, 2)

    # =========================
    # MOMENTUM INDICATORS
    # =========================
    macd = ta.macd(df["close"])
    mom_macd = int(macd["MACD_12_26_9"].iloc[-1] > macd["MACDs_12_26_9"].iloc[-1])

    rsi = ta.rsi(df["close"], length=14)
    mom_rsi = int(rsi.iloc[-1] > 50)

    adx = ta.adx(df["high"], df["low"], df["close"])
    mom_adx = int(adx["ADX_14"].iloc[-1] > 20)

    momentum_score = np.mean([mom_macd, mom_rsi, mom_adx])
    result["Momentum Score"] = round(momentum_score, 2)

    # =========================
    # VOLUME INDICATORS
    # =========================
    obv = ta.obv(df["close"], df["volume"])
    mfi = ta.mfi(df["high"], df["low"], df["close"], df["volume"], length=14)

    vol_obv = int(obv.diff().iloc[-1] > 0)
    vol_mfi = int(mfi.iloc[-1] > 50)

    volume_score = np.mean([vol_obv, vol_mfi])
    result["Volume Score"] = round(volume_score, 2)

    # =========================
    # FINAL WEIGHTED SCORE
    # =========================
    tmv = 0.4 * trend_score + 0.4 * momentum_score + 0.2 * volume_score
    result["TMV Score"] = round(tmv, 2)

    # =========================
    # TREND DIRECTION
    # =========================
    if trend_score > 0.6 and momentum_score > 0.6:
        direction = "Bullish"
    elif trend_score < 0.4 and momentum_score < 0.4:
        direction = "Bearish"
    else:
        direction = "Neutral"
    result["Trend Direction"] = direction

    # =========================
    # REVERSAL PROBABILITY (simple rule-based estimate)
    # =========================
    reversal = 1 - tmv if direction != "Neutral" else 0.5
    result["Reversal Probability"] = round(reversal, 2)

    return result
