import pandas as pd
import numpy as np
import pandas_ta as ta

def calculate_scores(df):
    scores = {}

    # Ensure timestamp is datetime
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)

    # Price columns required
    if not {'open', 'high', 'low', 'close', 'volume'}.issubset(df.columns):
        return {}

    # Trend Indicators
    ema8 = ta.ema(df['close'], length=8)
    ema21 = ta.ema(df['close'], length=21)
    supertrend = ta.supertrend(df['high'], df['low'], df['close'])["SUPERT_7_3.0"]
    trend_score = ((ema8 > ema21).astype(int) + (df['close'] > supertrend).astype(int)) / 2

    # Momentum Indicators
    macd = ta.macd(df['close'])
    rsi = ta.rsi(df['close'])
    adx = ta.adx(df['high'], df['low'], df['close'])
    momentum_score = (
        (macd['MACD_12_26_9'] > macd['MACDs_12_26_9']).astype(int) +
        (rsi > 50).astype(int) +
        (adx['ADX_14'] > 20).astype(int)
    ) / 3

    # Volume Indicators
    obv = ta.obv(df['close'], df['volume'])
    mfi = ta.mfi(df['high'], df['low'], df['close'], df['volume'])
    volume_score = (
        (obv.diff() > 0).astype(int) +
        (mfi > 50).astype(int)
    ) / 2

    # Weighted TMV Score
    weights = {
        'Trend Score': 0.4,
        'Momentum Score': 0.35,
        'Volume Score': 0.25
    }

    scores['Trend Score'] = trend_score.iloc[-1]
    scores['Momentum Score'] = momentum_score.iloc[-1]
    scores['Volume Score'] = volume_score.iloc[-1]
    scores['TMV Score'] = (
        scores['Trend Score'] * weights['Trend Score'] +
        scores['Momentum Score'] * weights['Momentum Score'] +
        scores['Volume Score'] * weights['Volume Score']
    )

    # Direction
    if scores['Trend Score'] >= 0.75:
        scores['Trend Direction'] = 'Bullish'
    elif scores['Trend Score'] <= 0.25:
        scores['Trend Direction'] = 'Bearish'
    else:
        scores['Trend Direction'] = 'Neutral'

    # Reversal Probability
    recent_rsi = rsi.iloc[-5:]
    reversal = ((recent_rsi < 30) | (recent_rsi > 70)).sum() / 5
    scores['Reversal Probability'] = reversal

    return scores
