import pandas as pd
import numpy as np
import pandas_ta as ta

def calculate_scores(df):
    scores = {}

    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)

    if not {'open', 'high', 'low', 'close', 'volume'}.issubset(df.columns):
        return {}

    # Trend signals
    ema8 = ta.ema(df['close'], length=8)
    ema21 = ta.ema(df['close'], length=21)
    supertrend = ta.supertrend(df['high'], df['low'], df['close'])["SUPERT_7_3.0"]

    trend_score = 0
    if ema8.iloc[-1] > ema21.iloc[-1]:
        trend_score += 1
    if df['close'].iloc[-1] > supertrend.iloc[-1]:
        trend_score += 1

    # Momentum signals
    macd = ta.macd(df['close'])
    rsi = ta.rsi(df['close'])
    adx = ta.adx(df['high'], df['low'], df['close'])

    momentum_score = 0
    if macd['MACD_12_26_9'].iloc[-1] > macd['MACDs_12_26_9'].iloc[-1]:
        momentum_score += 1
    if rsi.iloc[-1] > 50:
        momentum_score += 1
    if adx['ADX_14'].iloc[-1] > 20:
        momentum_score += 1

    # Volume signals
    obv = ta.obv(df['close'], df['volume'])
    mfi = ta.mfi(df['high'], df['low'], df['close'], df['volume'])

    volume_score = 0
    if obv.diff().iloc[-1] > 0:
        volume_score += 1
    if mfi.iloc[-1] > 50:
        volume_score += 1

    # Final TMV Score (rule-based)
    tmv_score = 0
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

    scores['Trend Score'] = trend_score / 2
    scores['Momentum Score'] = momentum_score / 3
    scores['Volume Score'] = volume_score / 2
    scores['TMV Score'] = round(tmv_score, 2)

    # Trend Direction
    if trend_score == 2:
        scores['Trend Direction'] = 'Bullish'
    elif trend_score == 0:
        scores['Trend Direction'] = 'Bearish'
    else:
        scores['Trend Direction'] = 'Neutral'

    # Reversal Probability (RSI extremes)
    recent_rsi = rsi.tail(5)
    reversal = ((recent_rsi < 30) | (recent_rsi > 70)).sum() / 5
    scores['Reversal Probability'] = round(reversal, 2)

    return scores
