# utils/indicators.py
import numpy as np
import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1/length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/length, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-12)
    return 100 - (100 / (1 + rs))


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1/length, adjust=False).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = true_range(high, low, close)

    atr_sm = tr.ewm(alpha=1/length, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=high.index).ewm(alpha=1/length, adjust=False).mean() / (atr_sm + 1e-12)
    minus_di = 100 * pd.Series(minus_dm, index=high.index).ewm(alpha=1/length, adjust=False).mean() / (atr_sm + 1e-12)

    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-12))
    adx_val = dx.ewm(alpha=1/length, adjust=False).mean()
    return adx_val


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0.0)
    return (direction * volume).cumsum()


def mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, length: int = 14) -> pd.Series:
    typical = (high + low + close) / 3.0
    money_flow = typical * volume
    pos_flow = money_flow.where(typical > typical.shift(1), 0.0)
    neg_flow = money_flow.where(typical < typical.shift(1), 0.0)
    pos_sum = pos_flow.rolling(length).sum()
    neg_sum = neg_flow.rolling(length).sum()
    mfr = pos_sum / (neg_sum + 1e-12)
    return 100 - (100 / (1 + mfr))


def calculate_scores(df: pd.DataFrame) -> dict:
    """
    Input df must have: date, open, high, low, close, volume
    Output keys MUST include 'TMV Score'
    """
    required = {"date", "open", "high", "low", "close", "volume"}
    if df is None or df.empty or not required.issubset(df.columns):
        return {"error": "Invalid/empty OHLC"}

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    if df.empty:
        return {"error": "No valid candle timestamps"}

    # hard sufficiency gate
    if len(df) < 60:
        return {
            "TMV Score": np.nan,
            "Confidence": 0,
            "Trend Direction": "UNKNOWN",
            "Regime": "THIN_DATA",
            "Reversal Probability": np.nan,
            "CandleTime": df["date"].iloc[-1].isoformat(),
            "warning": f"Not enough candles ({len(df)})",
        }

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    vol = df["volume"].astype(float)

    ema8 = ema(close, 8)
    ema21 = ema(close, 21)
    atr14 = atr(high, low, close, 14)
    adx14 = adx(high, low, close, 14)

    td = "Neutral"
    if ema8.iloc[-1] > ema21.iloc[-1]:
        td = "Bullish"
    elif ema8.iloc[-1] < ema21.iloc[-1]:
        td = "Bearish"

    sep = float(abs(ema8.iloc[-1] - ema21.iloc[-1]))
    sep_norm = sep / (float(atr14.iloc[-1]) + 1e-12)
    adx_now = float(adx14.iloc[-1])

    regime = "TREND" if (adx_now >= 20 and sep_norm >= 0.35) else "RANGE"

    rsi14 = rsi(close, 14)
    _, _, macd_hist = macd(close, 12, 26, 9)

    obv_line = obv(close, vol)
    mfi14 = mfi(high, low, close, vol, 14)

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
    if float(rsi14.iloc[-1]) > 55:
        momentum_score += 0.5
    if float(macd_hist.iloc[-1]) > 0:
        momentum_score += 0.5

    volume_score = 0.0
    if float(obv_line.diff().iloc[-1]) > 0:
        volume_score += 0.5
    if float(mfi14.iloc[-1]) > 50:
        volume_score += 0.5

    if regime == "TREND":
        w_trend, w_mom, w_vol = 0.45, 0.40, 0.15
    else:
        w_trend, w_mom, w_vol = 0.30, 0.35, 0.35

    tmv = (trend_score * w_trend + momentum_score * w_mom + volume_score * w_vol) * 100.0
    tmv = float(round(tmv, 1))

    confluence = (trend_score + momentum_score + volume_score) / 3.0
    clarity = min(1.0, max(0.0, (adx_now - 15) / 20))
    overheating = 0.25 if (float(rsi14.iloc[-1]) > 75 or float(rsi14.iloc[-1]) < 25) else 0.0

    conf = (0.55 * confluence + 0.45 * clarity) - overheating
    conf = int(max(0, min(100, round(conf * 100))))

    recent = rsi14.dropna().tail(8)
    rev = float(((recent < 30) | (recent > 70)).sum() / len(recent)) if len(recent) else np.nan

    return {
        "TMV Score": tmv,
        "Confidence": conf,
        "Trend Direction": td,
        "Regime": regime,
        "Reversal Probability": round(rev, 2) if isinstance(rev, float) else rev,
        "CandleTime": df["date"].iloc[-1].isoformat(),
    }
