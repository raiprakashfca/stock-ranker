import pandas as pd
import numpy as np

def calculate_indicators(df: pd.DataFrame) -> dict:
    """
    Calculates Trend, Momentum, and Volume indicators and scores for a given OHLCV DataFrame.
    Returns a dictionary with all scores and components.
    """

    # Validate input
    if df.empty or len(df) < 20:
        raise ValueError("Insufficient data for indicator calculation")

    result = {}

    # ============================
    # TREND INDICATORS
    # ============================

    # EMA crossover
    ema_8 = df['close'].ewm(span=8, adjust=False).mean()
    ema_21 = df['close'].ewm(span=21, adjust=False).mean()
    result["Trend_EMA"] = int(ema_8.iloc[-1] > ema_21.iloc[-1])

    # SuperTrend Indicator (simplified version)
    atr = df['high'].rolling(10).max() - df['low'].rolling(10).min()
    hl2 = (df['high'] + df['low']) / 2
    supertrend = hl2 - 1.5 * atr
    result["Trend_Supertrend"] = int(df['close'].iloc[-1] > supertrend.iloc[-1])

    # Hull Moving Average (HMA)
    def hma(series, period):
        wma_half = series.rolling(int(period / 2)).mean()
        wma_full = series.rolling(period).mean()
        raw_hma = 2 * wma_half - wma_full
        return raw_hma.rolling(int(np.sqrt(period))).mean()

    hma_14 = hma(df['close'], 14)
    result["Trend_HMA"] = int(df['close'].iloc[-1] > hma_14.iloc[-1])

    # Final trend score (0 to 3)
    trend_score = result["Trend_EMA"] + result["Trend_Supertrend"] + result["Trend_HMA"]
    result["Trend_Score"] = trend_score


    # ============================
    # MOMENTUM INDICATORS
    # ============================

    # RSI (Relative Strength Index)
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    result["RSI"] = rsi.iloc[-1]
    result["Momentum_RSI"] = int(result["RSI"] > 55)

    # MACD
    ema_12 = df['close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['close'].ewm(span=26, adjust=False).mean()
    macd = ema_12 - ema_26
    signal = macd.ewm(span=9, adjust=False).mean()
    result["MACD"] = macd.iloc[-1]
    result["Momentum_MACD"] = int(macd.iloc[-1] > signal.iloc[-1])

    # ADX (Average Directional Index)
    df['TR'] = df[['high', 'low', 'close']].max(axis=1) - df[['high', 'low', 'close']].min(axis=1)
    df['+DM'] = df['high'].diff()
    df['-DM'] = -df['low'].diff()
    df['+DM'] = df['+DM'].where((df['+DM'] > df['-DM']) & (df['+DM'] > 0), 0.0)
    df['-DM'] = df['-DM'].where((df['-DM'] > df['+DM']) & (df['-DM'] > 0), 0.0)
    tr14 = df['TR'].rolling(14).sum()
    plus_dm14 = df['+DM'].rolling(14).sum()
    minus_dm14 = df['-DM'].rolling(14).sum()
    plus_di = 100 * (plus_dm14 / tr14)
    minus_di = 100 * (minus_dm14 / tr14)
    dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di))
    adx = dx.rolling(14).mean()
    result["ADX"] = adx.iloc[-1]
    result["Momentum_ADX"] = int(result["ADX"] > 20)

    # Final momentum score (0 to 3)
    momentum_score = result["Momentum_RSI"] + result["Momentum_MACD"] + result["Momentum_ADX"]
    result["Momentum_Score"] = momentum_score


    # ============================
    # VOLUME INDICATORS
    # ============================

    # OBV (On Balance Volume)
    obv = [0]
    for i in range(1, len(df)):
        if df['close'].iloc[i] > df['close'].iloc[i - 1]:
            obv.append(obv[-1] + df['volume'].iloc[i])
        elif df['close'].iloc[i] < df['close'].iloc[i - 1]:
            obv.append(obv[-1] - df['volume'].iloc[i])
        else:
            obv.append(obv[-1])
    df['OBV'] = obv
    result["OBV_Change"] = df['OBV'].iloc[-1] - df['OBV'].iloc[-2]
    result["Volume_OBV"] = int(result["OBV_Change"] > 0)

    # MFI (Money Flow Index)
    tp = (df['high'] + df['low'] + df['close']) / 3
    mf = tp * df['volume']
    pos_mf = mf.where(tp > tp.shift(1), 0)
    neg_mf = mf.where(tp < tp.shift(1), 0)
    pos_sum = pos_mf.rolling(14).sum()
    neg_sum = neg_mf.rolling(14).sum()
    mfi = 100 - (100 / (1 + (pos_sum / neg_sum)))
    result["MFI"] = mfi.iloc[-1]
    result["Volume_MFI"] = int(result["MFI"] > 50)

    # Final volume score (0 to 2)
    volume_score = result["Volume_OBV"] + result["Volume_MFI"]
    result["Volume_Score"] = volume_score

    # ============================
    # COMPOSITE SCORE & TREND REVERSAL
    # ============================

    # Composite score (can later be weighted)
    total_score = trend_score + momentum_score + volume_score
    result["Score"] = total_score

    # Simple trend reversal probability (based on overbought RSI or divergence in indicators)
    result["Reversal_Probability"] = (
        int(result["RSI"] > 70) + int(result["MACD"] < 0) + int(result["OBV_Change"] < 0)
    ) / 3 * 100

    return result
