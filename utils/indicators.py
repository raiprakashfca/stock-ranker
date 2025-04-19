import numpy as np
import pandas_ta as ta

def calculate_scores(df):
    df = df.copy()
    df.dropna(inplace=True)

    # Calculate indicators
    df["EMA8"] = ta.ema(df["close"], length=8)
    df["EMA21"] = ta.ema(df["close"], length=21)
    df["MACD"] = ta.macd(df["close"]).iloc[:, 0]  # macd line
    df["RSI"] = ta.rsi(df["close"], length=14)
    df["ADX"] = ta.adx(df["high"], df["low"], df["close"]).iloc[:, 0]
    df["OBV"] = ta.obv(df["close"], df["volume"])
    df["MFI"] = ta.mfi(df["high"], df["low"], df["close"], df["volume"])
    df["SUPERT"] = ta.supertrend(df["high"], df["low"], df["close"]).iloc[:, 0]
    df["HULL"] = ta.hma(df["close"], length=14)
    df["ALLIGATOR"] = ta.sma(df["close"], length=13)
    df["FAMA"] = ta.linreg(df["close"], length=20)

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    # Trend
    scores = {
        "ema_score": 1 if latest["EMA8"] > latest["EMA21"] else 0,
        "alligator_score": 1 if latest["close"] > latest["ALLIGATOR"] else 0,
        "fractal_ama_score": 1 if latest["close"] > latest["FAMA"] else 0,
        "hull_ma_score": 1 if latest["close"] > latest["HULL"] else 0,
        "supertrend_score": 1 if latest["close"] > latest["SUPERT"] else 0,

        # Momentum
        "macd_score": 1 if latest["MACD"] > 0 else 0,
        "rsi_score": 1 if latest["RSI"] > 50 else 0,
        "adx_score": 1 if latest["ADX"] > 20 else 0,

        # Volume
        "obv_score": 1 if latest["OBV"] > prev["OBV"] else 0,
        "mfi_score": 1 if 45 <= latest["MFI"] <= 80 else 0,
    }

    # Weights
    trend_weights = {
        "ema_score": 0.25,
        "alligator_score": 0.15,
        "fractal_ama_score": 0.20,
        "hull_ma_score": 0.20,
        "supertrend_score": 0.20
    }
    momentum_weights = {
        "macd_score": 0.40,
        "rsi_score": 0.30,
        "adx_score": 0.30
    }
    volume_weights = {
        "obv_score": 0.60,
        "mfi_score": 0.40
    }

    trend_score = sum([scores[k] * w for k, w in trend_weights.items()])
    momentum_score = sum([scores[k] * w for k, w in momentum_weights.items()])
    volume_score = sum([scores[k] * w for k, w in volume_weights.items()])
    total_score = trend_score * 0.5 + momentum_score * 0.35 + volume_score * 0.15

    return {
        "Trend Score": trend_score,
        "Momentum Score": momentum_score,
        "Volume Score": volume_score,
        "Total Score": total_score
    }
