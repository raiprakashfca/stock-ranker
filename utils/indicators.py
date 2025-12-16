# utils/indicators.py
import pandas as pd
import numpy as np
import pandas_ta as ta

def _need(df: pd.DataFrame, n: int) -> bool:
    return df is not None and not df.empty and len(df) >= n

def calculate_scores(df: pd.DataFrame) -> dict:
    """
    Returns:
      TMV Score (0-100), Confidence (0-100),
      Trend Direction, Regime, Reversal Probability,
      CandleTime (last candle)
    """
    scores = {}

    required = {"date", "open", "high", "low", "close", "volume"}
    if df is None or df.empty or not required.issubset(df.columns):
        return {"error": "Invalid/empty OHLC"}

    # ensure types
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    if df.empty:
        return {"error": "No valid candle timestamps"}

    scores["CandleTime"] = df["date"].iloc[-1].isoformat()

    # hard sufficiency gates
    if len(df) < 60:
        return {
            "TMV Score": np.nan,
            "Confidence": 0,
            "Trend Direction": "UNKNOWN",
            "Regime": "THIN_DATA",
            "Reversal Probability": np.nan,
            "CandleTime": scores["CandleTime"],
            "warning": f"Not enough candles ({len(df)})"
        }

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low  = df["low"].astype(float)
    vol  = df["volume"].astype(float)

    # --- Trend block
    ema8 = ta.ema(close, length=8)
    ema21 = ta.ema(close, length=21)
    atr14 = ta.atr(high, low, close, length=14)
    adx14 = ta.adx(high, low, close, length=14)["ADX_14"]

    # Trend direction
    td = "Neutral"
    if ema8.iloc[-1] > ema21.iloc[-1]:
        td = "Bullish"
    elif ema8.iloc[-1] < ema21.iloc[-1]:
        td = "Bearish"
    scores["Trend Direction"] = td

    # Regime: trending vs range (ADX + EMA separation normalized by ATR)
    sep = abs(ema8.iloc[-1] - ema21.iloc[-1])
    sep_norm = float(sep / (atr14.iloc[-1] + 1e-9))
    adx = float(adx14.iloc[-1])

    if adx >= 20 and sep_norm >= 0.35:
        regime = "TREND"
    else:
        regime = "RANGE"
    scores["Regime"] = regime

    # --- Momentum block
    rsi14 = ta.rsi(close, length=14)
    macd = ta.macd(close, fast=12, slow=26, signal=9)
    macd_hist = macd.iloc[:, 2]  # MACDh

    # --- Volume block
    obv = ta.obv(close, vol)
    mfi14 = ta.mfi(high, low, close, vol, length=14)

    # Convert to compact rule-scores (0..1)
    trend_score = 0.0
    if td == "Bullish":
        trend_score += 0.5
        if close.iloc[-1] > ema8.iloc[-1]:
            trend_score += 0.5
    elif td == "Bearish":
        trend_score += 0.5
        if close.iloc[-1] < ema8.iloc[-1]:
            trend_score += 0.5

    momentum_score = 0.0
    if rsi14.iloc[-1] > 55:
        momentum_score += 0.5
    if macd_hist.iloc[-1] > 0:
        momentum_score += 0.5

    volume_score = 0.0
    if obv.diff().iloc[-1] > 0:
        volume_score += 0.5
    if mfi14.iloc[-1] > 50:
        volume_score += 0.5

    # Weighting by regime (this is the “trader brain” part)
    if regime == "TREND":
        w_trend, w_mom, w_vol = 0.45, 0.40, 0.15
    else:  # RANGE
        w_trend, w_mom, w_vol = 0.30, 0.35, 0.35

    tmv = (trend_score * w_trend + momentum_score * w_mom + volume_score * w_vol) * 100.0
    tmv = float(round(tmv, 1))
    scores["TMV Score"] = tmv

    # Confidence: confluence + clarity (ADX) + not-overheated
    confluence = (trend_score + momentum_score + volume_score) / 3.0  # 0..1
    clarity = min(1.0, max(0.0, (adx - 15) / 20))  # 15->0, 35->1
    overheating = 0.0
    if rsi14.iloc[-1] > 75 or rsi14.iloc[-1] < 25:
        overheating = 0.25  # reduce confidence in extremes

    conf = (0.55 * confluence + 0.45 * clarity) - overheating
    conf = int(max(0, min(100, round(conf * 100))))
    scores["Confidence"] = conf

    # Reversal probability: RSI extremes frequency in last 8 candles
    recent = rsi14.dropna().tail(8)
    if len(recent) > 0:
        rev = ((recent < 30) | (recent > 70)).sum() / len(recent)
        scores["Reversal Probability"] = float(round(rev, 2))
    else:
        scores["Reversal Probability"] = np.nan

    return scores
