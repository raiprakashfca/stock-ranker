import pandas_ta as ta
import numpy as np

def calculate_scores(df):
    trend_score = 0
    momentum_score = 0
    volume_score = 0

    # Trend Indicators
    df['EMA_8'] = ta.ema(df['Close'], length=8)
    df['EMA_21'] = ta.ema(df['Close'], length=21)
    df['HMA_21'] = ta.hma(df['Close'], length=21)
    st = ta.supertrend(df['High'], df['Low'], df['Close'], length=10, multiplier=3.0)
    df['ST'] = st[f'SUPERTd_10_3.0']

    if df['EMA_8'].iloc[-1] > df['EMA_21'].iloc[-1]:
        trend_score += 1
    if df['HMA_21'].iloc[-1] > df['HMA_21'].iloc[-2]:
        trend_score += 1
    if df['ST'].iloc[-1] == 1.0:
        trend_score += 1

    # Alligator Indicator
    df['Jaw'] = ta.sma(df['Close'], length=13).shift(8)
    df['Teeth'] = ta.sma(df['Close'], length=8).shift(5)
    df['Lips'] = ta.sma(df['Close'], length=5).shift(3)

    if df['Lips'].iloc[-1] > df['Teeth'].iloc[-1] > df['Jaw'].iloc[-1]:
        trend_score += 1

    # Fractal AMA (simple slope of smoothed close)
    smoothed = df['Close'].rolling(window=5).mean()
    if smoothed.iloc[-1] > smoothed.iloc[-2]:
        trend_score += 1

    # Momentum Indicators
    macd = ta.macd(df['Close'])
    df['MACD'], df['MACD_signal'] = macd['MACD_12_26_9'], macd['MACDs_12_26_9']
    df['RSI'] = ta.rsi(df['Close'], length=14)
    adx = ta.adx(df['High'], df['Low'], df['Close'])
    df['ADX'], df['+DI'], df['-DI'] = adx['ADX_14'], adx['DMP_14'], adx['DMN_14']

    if df['MACD'].iloc[-1] > df['MACD_signal'].iloc[-1]:
        momentum_score += 1
    if 55 < df['RSI'].iloc[-1] < 70:
        momentum_score += 1
    if df['ADX'].iloc[-1] > 20 and df['+DI'].iloc[-1] > df['-DI'].iloc[-1]:
        momentum_score += 1

    # Volume Indicators
    df['OBV'] = ta.obv(df['Close'], df['Volume'])
    df['MFI'] = ta.mfi(df['High'], df['Low'], df['Close'], df['Volume'])

    if df['OBV'].iloc[-1] > df['OBV'].iloc[-2]:
        volume_score += 1
    if 55 < df['MFI'].iloc[-1] < 80:
        volume_score += 1

    total_score = trend_score + momentum_score + volume_score

    return {
        "Trend": trend_score,
        "Momentum": momentum_score,
        "Volume": volume_score,
        "Total Score": total_score
    }
