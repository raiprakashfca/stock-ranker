# utils/indicators.py
import pandas as pd

def calculate_scores(ohlc: pd.DataFrame) -> dict:
    """
    Input: OHLC dataframe indexed by datetime with columns:
      open, high, low, close, volume
    Output: dict with TMV Score + supporting fields.

    Uses 'ta' library (installable) and avoids pandas_ta.
    """
    if ohlc is None or ohlc.empty:
        return {}

    df = ohlc.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        # Try to find date column fallback
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
        else:
            return {}

    df = df.sort_index()
    if len(df) < 80:
        return {}  # not enough candles for stable MACD/ADX etc.

    import ta

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low  = df["low"].astype(float)
    vol  = df["volume"].astype(float)

    # Indicators
    ema8  = ta.trend.EMAIndicator(close, window=8).ema_indicator()
    ema21 = ta.trend.EMAIndicator(close, window=21).ema_indicator()

    macd = ta.trend.MACD(close)
    macd_line = macd.macd()
    macd_sig  = macd.macd_signal()
    macd_hist = macd.macd_diff()

    rsi = ta.momentum.RSIIndicator(close, window=14).rsi()
    adx = ta.trend.ADXIndicator(high, low, close, window=14).adx()

    atr = ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range()

    # Volume proxies
    obv = ta.volume.OnBalanceVolumeIndicator(close, vol).on_balance_volume()
    mfi = ta.volume.MFIIndicator(high, low, close, vol, window=14).money_flow_index()

    # Latest
    last = -1

    # Trend score (0–1)
    trend = 0.0
    if ema8.iloc[last] > ema21.iloc[last]:
        trend += 0.6
    # Normalize price distance from EMA21 using ATR
    dist = (close.iloc[last] - ema21.iloc[last]) / (atr.iloc[last] + 1e-9)
    trend += max(min(dist * 0.2, 0.4), -0.4)  # clamp
    trend = max(min(trend, 1.0), 0.0)

    # Momentum score (0–1)
    mom = 0.0
    if macd_line.iloc[last] > macd_sig.iloc[last]:
        mom += 0.5
    # RSI centered at 50
    mom += max(min((rsi.iloc[last] - 50) / 50 * 0.5, 0.5), -0.5)
    mom = max(min(mom, 1.0), 0.0)

    # Volume score (0–1)
    vol_score = 0.0
    if obv.diff().iloc[last] > 0:
        vol_score += 0.5
    if mfi.iloc[last] > 50:
        vol_score += 0.5

    # TMV weighted score
    tmv = 0.45 * trend + 0.40 * mom + 0.15 * vol_score
    tmv = round(float(tmv), 2)

    # Regime / confidence
    adx_v = float(adx.iloc[last])
    if adx_v >= 25:
        regime = "Trending"
        confidence = "High"
    elif adx_v >= 18:
        regime = "Developing"
        confidence = "Medium"
    else:
        regime = "Choppy"
        confidence = "Low"

    # Trend direction label
    if ema8.iloc[last] > ema21.iloc[last] and macd_hist.iloc[last] > 0:
        direction = "Bullish"
    elif ema8.iloc[last] < ema21.iloc[last] and macd_hist.iloc[last] < 0:
        direction = "Bearish"
    else:
        direction = "Neutral"

    # Reversal probability (simple but useful)
    # Higher if RSI extreme or big mean-reversion distance
    rev = 0.0
    if rsi.iloc[last] >= 70 or rsi.iloc[last] <= 30:
        rev += 0.6
    if abs(dist) >= 1.5:
        rev += 0.4
    rev = round(float(min(rev, 1.0)), 2)

    # Human-readable reason
    reason_parts = []
    reason_parts.append(f"EMA8 {'>' if ema8.iloc[last] > ema21.iloc[last] else '<='} EMA21")
    reason_parts.append(f"MACD {'bull' if macd_line.iloc[last] > macd_sig.iloc[last] else 'bear'}")
    reason_parts.append(f"RSI={round(float(rsi.iloc[last]),1)}")
    reason_parts.append(f"ADX={round(adx_v,1)}")
    signal_reason = " | ".join(reason_parts)

    return {
        "TMV Score": tmv,
        "Trend Direction": direction,
        "Regime": regime,
        "Confidence": confidence,
        "SignalReason": signal_reason,
        "Reversal Probability": rev,
    }
