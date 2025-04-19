import pandas as pd
import numpy as np
import ta

def calculate_scores(df):
    df = df.copy()
    df = df.dropna().reset_index(drop=True)

    # Trend Indicators
    ema_fast = ta.trend.ema_indicator(df['close'], window=8).ema_indicator()
    ema_slow = ta.trend.ema_indicator(df['close'], window=21).ema_indicator()
    trend_score = np.where(ema_fast > ema_slow, 1, 0)

    # Momentum Indicators
    rsi = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    macd_diff = ta.trend.MACD(df['close']).macd_diff()
    momentum_score = np.where((rsi > 50) & (macd_diff > 0), 1, 0)

    # Volume Indicators
    obv = ta.volume.OnBalanceVolumeIndicator(df['close'], df['volume']).on_balance_volume()
    mfi = ta.volume.MFIIndicator(high=df['high'], low=df['low'], close=df['close'], volume=df['volume']).money_flow_index()
    volume_score = np.where((mfi > 50), 1, 0)

    # Direction determination
    if trend_score[-1] and momentum_score[-1]:
        trend_direction = "Bullish"
    elif not trend_score[-1] and not momentum_score[-1]:
        trend_direction = "Bearish"
    else:
        trend_direction = "Neutral"

    # Reversal Probability: dummy logic based on RSI slope
    recent_rsi = rsi[-5:].values
    rsi_slope = np.polyfit(np.arange(len(recent_rsi)), recent_rsi, 1)[0]
    reversal_probability = np.clip(1 - abs(rsi_slope) / 2, 0, 1)

    # Aggregate scores
    trend_val = trend_score[-1]
    momentum_val = momentum_score[-1]
    volume_val = volume_score[-1]
    total_score = (trend_val + momentum_val + volume_val) / 3

    return {
        "Trend Score": round(float(trend_val), 2),
        "Momentum Score": round(float(momentum_val), 2),
        "Volume Score": round(float(volume_val), 2),
        "Total Score": round(float(total_score), 2),
        "Trend Direction": trend_direction,
        "Reversal Probability": round(float(reversal_probability), 2)
    }
