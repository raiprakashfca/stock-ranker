# utils/indicators.py
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, List

import numpy as np
import pandas as pd


# -----------------------------
# Small indicator helpers
# -----------------------------
def _to_float_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)

def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False, min_periods=span).mean()

def _sma(s: pd.Series, window: int) -> pd.Series:
    return s.rolling(window, min_periods=window).mean()

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    rs = avg_gain / (avg_loss.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    return rsi

def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr

def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = _true_range(high, low, close)
    return tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()

def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
    # Wilder’s ADX
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = _true_range(high, low, close)

    atr = tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    plus_di = 100 * pd.Series(plus_dm, index=high.index).ewm(alpha=1/period, adjust=False, min_periods=period).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=high.index).ewm(alpha=1/period, adjust=False, min_periods=period).mean() / atr

    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx = dx.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    return adx, plus_di, minus_di

def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0.0)
    return (direction * volume).fillna(0.0).cumsum()

def _mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 14) -> pd.Series:
    tp = (high + low + close) / 3.0
    raw_mf = tp * volume
    pos_mf = raw_mf.where(tp.diff() > 0, 0.0)
    neg_mf = raw_mf.where(tp.diff() < 0, 0.0).abs()
    pos_sum = pos_mf.rolling(period, min_periods=period).sum()
    neg_sum = neg_mf.rolling(period, min_periods=period).sum().replace(0, np.nan)
    mfr = pos_sum / neg_sum
    mfi = 100 - (100 / (1 + mfr))
    return mfi

def _bbands(close: pd.Series, period: int = 20, mult: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    mid = _sma(close, period)
    std = close.rolling(period, min_periods=period).std()
    upper = mid + mult * std
    lower = mid - mult * std
    width = (upper - lower) / mid.replace(0, np.nan)  # relative width
    return lower, mid, upper, width

def _clip(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))

def _safe_last(s: pd.Series) -> Optional[float]:
    if s is None or len(s) == 0:
        return None
    v = s.dropna()
    if len(v) == 0:
        return None
    return float(v.iloc[-1])

def _slope_last(s: pd.Series, lookback: int = 5) -> Optional[float]:
    v = s.dropna()
    if len(v) < lookback:
        return None
    y = v.iloc[-lookback:].values.astype(float)
    x = np.arange(len(y), dtype=float)
    # simple linear slope
    denom = ((x - x.mean()) ** 2).sum()
    if denom == 0:
        return None
    slope = ((x - x.mean()) * (y - y.mean())).sum() / denom
    return float(slope)

def _pct_rank(series: pd.Series, value: float) -> float:
    v = series.dropna().values
    if len(v) < 10:
        return 0.5
    return float((v <= value).mean())


# -----------------------------
# Main scoring
# -----------------------------
def calculate_scores(df: pd.DataFrame) -> Dict[str, object]:
    """
    Trader-grade TMV scoring (change-based).
    Expects columns: date, open, high, low, close, volume
    Returns keys used by your updater/app:
      TMV Score, Confidence, Trend Direction, Regime, Reversal Probability, CandleTime
    Plus:
      SignalReason, TrendScore, MomentumScore, VolumeScore, VolatilityScore
    """

    required = {"date", "open", "high", "low", "close", "volume"}
    if not required.issubset(df.columns):
        return {"TMV Score": None, "Confidence": 0.0, "Trend Direction": "Neutral", "Regime": "Unknown",
                "Reversal Probability": 0.0, "CandleTime": None, "SignalReason": "Missing columns"}

    d = df.copy()

    # Clean & sort
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date")
    for col in ["open", "high", "low", "close", "volume"]:
        d[col] = _to_float_series(d[col])

    d = d.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    if len(d) < 60:
        return {"TMV Score": None, "Confidence": 0.0, "Trend Direction": "Neutral", "Regime": "Unknown",
                "Reversal Probability": 0.0, "CandleTime": None, "SignalReason": "Not enough candles (need ~60+)"}

    close = d["close"]
    high = d["high"]
    low = d["low"]
    vol = d["volume"].fillna(0.0)

    candle_time = d["date"].iloc[-1].to_pydatetime().isoformat()

    # Core indicators
    ema8 = _ema(close, 8)
    ema21 = _ema(close, 21)
    ema50 = _ema(close, 50)

    rsi14 = _rsi(close, 14)
    macd_line, macd_sig, macd_hist = _macd(close, 12, 26, 9)

    adx14, pdi, mdi = _adx(high, low, close, 14)
    atr14 = _atr(high, low, close, 14)

    obv = _obv(close, vol)
    mfi14 = _mfi(high, low, close, vol, 14)

    bb_low, bb_mid, bb_up, bb_width = _bbands(close, 20, 2.0)

    # Recent changes (delta features)
    def delta_now_prev(s: pd.Series, k: int = 3) -> float:
        v = s.dropna()
        if len(v) < 2 * k:
            return 0.0
        now = v.iloc[-k:].mean()
        prev = v.iloc[-2*k:-k].mean()
        if pd.isna(now) or pd.isna(prev):
            return 0.0
        return float(now - prev)

    # -------------------------
    # Trend Direction + TrendScore
    # -------------------------
    last_close = float(close.iloc[-1])
    last_ema8 = _safe_last(ema8) or last_close
    last_ema21 = _safe_last(ema21) or last_close
    last_ema50 = _safe_last(ema50) or last_close

    ema_stack_up = (last_close > last_ema21 > last_ema50) and (last_ema8 > last_ema21)
    ema_stack_dn = (last_close < last_ema21 < last_ema50) and (last_ema8 < last_ema21)

    ema21_slope = _slope_last(ema21, 8) or 0.0
    adx_val = _safe_last(adx14) or 0.0
    pdi_val = _safe_last(pdi) or 0.0
    mdi_val = _safe_last(mdi) or 0.0

    if ema_stack_up and pdi_val >= mdi_val:
        trend_dir = "Up"
    elif ema_stack_dn and mdi_val > pdi_val:
        trend_dir = "Down"
    else:
        trend_dir = "Neutral"

    # Trend score components (0..10-ish before clamp)
    trend_strength = 0.0
    # alignment
    trend_strength += 2.5 if ema_stack_up or ema_stack_dn else 0.5
    # direction confirmation
    trend_strength += 2.0 if (pdi_val - mdi_val) > 5 else 0.0
    trend_strength += 2.0 if (mdi_val - pdi_val) > 5 else 0.0
    # adx (trend quality)
    trend_strength += _clip((adx_val - 15) / 15 * 3.0, 0.0, 3.0)
    # slope
    trend_strength += _clip(abs(ema21_slope) * 50.0, 0.0, 2.0)

    trend_score = _clip(trend_strength, 0.0, 10.0)

    # -------------------------
    # MomentumScore (change-based)
    # -------------------------
    rsi_val = _safe_last(rsi14) or 50.0
    rsi_d = delta_now_prev(rsi14, 3)  # acceleration
    hist_val = _safe_last(macd_hist) or 0.0
    hist_d = delta_now_prev(macd_hist, 3)

    # normalize momentum around 50 RSI
    rsi_component = _clip((rsi_val - 50) / 50 * 4.0, -4.0, 4.0)
    accel_component = _clip(rsi_d * 0.6, -2.0, 2.0)
    macd_component = _clip(hist_val * 8.0, -2.5, 2.5)
    macd_accel = _clip(hist_d * 12.0, -1.5, 1.5)

    momentum_raw = 5.0 + rsi_component + accel_component + macd_component + macd_accel
    momentum_score = _clip(momentum_raw, 0.0, 10.0)

    # -------------------------
    # VolumeScore (confirmation + change)
    # -------------------------
    vol_sma20 = _sma(vol.replace(0, np.nan), 20)
    vol_ratio = (vol.iloc[-1] / (vol_sma20.iloc[-1] if not pd.isna(vol_sma20.iloc[-1]) else vol.iloc[-1])) if vol.iloc[-1] else 1.0
    obv_slope = _slope_last(obv, 8) or 0.0
    mfi_val = _safe_last(mfi14) or 50.0
    mfi_d = delta_now_prev(mfi14, 3)

    volume_raw = 4.0
    volume_raw += _clip((vol_ratio - 1.0) * 3.0, -1.0, 3.0)         # volume expansion
    volume_raw += _clip(obv_slope * 0.000001, -2.0, 2.0)            # obv trend (scaled)
    volume_raw += _clip((mfi_val - 50) / 50 * 2.0, -2.0, 2.0)       # mfi bias
    volume_raw += _clip(mfi_d * 0.4, -1.0, 1.0)                     # mfi acceleration

    volume_score = _clip(volume_raw, 0.0, 10.0)

    # -------------------------
    # Volatility / Regime
    # -------------------------
    bb_w_val = _safe_last(bb_width) or 0.0
    bb_w_rank = _pct_rank(bb_width.tail(200), bb_w_val)  # 0..1
    bb_w_d = delta_now_prev(bb_width, 3)

    # volatility score: reward expansion (breakout readiness)
    volat_raw = 5.0
    volat_raw += _clip((bb_w_rank - 0.5) * 6.0, -3.0, 3.0)
    volat_raw += _clip(bb_w_d * 40.0, -2.0, 2.0)
    volat_score = _clip(volat_raw, 0.0, 10.0)

    # Regime: Trend vs Range (ADX + band width)
    if adx_val >= 22 and bb_w_rank >= 0.45:
        regime = "Trend"
    elif adx_val <= 18 and bb_w_rank <= 0.45:
        regime = "Range"
    else:
        regime = "Transition"

    # -------------------------
    # TMV Score (weighted + confirmation)
    # -------------------------
    # weights (tunable)
    w_trend = 0.35
    w_mom = 0.35
    w_vol = 0.20
    w_vlt = 0.10

    tmv = (trend_score * w_trend) + (momentum_score * w_mom) + (volume_score * w_vol) + (volat_score * w_vlt)

    # confirmation boost/penalty:
    # If trend direction agrees with momentum bias, boost. If conflicts, penalize.
    mom_bias = "Up" if rsi_val >= 52 and hist_val >= 0 else "Down" if rsi_val <= 48 and hist_val <= 0 else "Neutral"
    agree = (trend_dir != "Neutral") and (mom_bias == trend_dir)
    conflict = (trend_dir != "Neutral") and (mom_bias != "Neutral") and (mom_bias != trend_dir)

    if agree:
        tmv += 0.6
    if conflict:
        tmv -= 0.8

    tmv = _clip(tmv, 0.0, 10.0)

    # -------------------------
    # Confidence (0..1): agreement + strength + data sufficiency
    # -------------------------
    conf = 0.35
    conf += 0.15 if agree else 0.0
    conf += 0.10 if (adx_val >= 20) else 0.0
    conf += 0.10 if (vol_ratio >= 1.15) else 0.0
    conf += 0.10 if (abs(hist_d) > 0) else 0.0
    conf = _clip(conf, 0.0, 1.0)

    # -------------------------
    # Reversal Probability (0..1): extremes + band touch + exhaustion
    # -------------------------
    # Basic exhaustion: RSI extreme AND price near outer band AND ADX falling (trend tiring)
    near_upper = bool(last_close >= float(bb_up.iloc[-1]) if not pd.isna(bb_up.iloc[-1]) else False)
    near_lower = bool(last_close <= float(bb_low.iloc[-1]) if not pd.isna(bb_low.iloc[-1]) else False)
    adx_d = delta_now_prev(adx14, 3)

    rev = 0.10
    if rsi_val >= 70 and near_upper:
        rev += 0.35
    if rsi_val <= 30 and near_lower:
        rev += 0.35
    if adx_d < 0 and adx_val >= 18:
        rev += 0.15
    # squeeze breakout is NOT reversal; lower reversal probability in expansion
    if bb_w_d > 0:
        rev -= 0.10

    reversal_prob = _clip(rev, 0.0, 1.0)

    # -------------------------
    # Signal reason (human-readable)
    # -------------------------
    reasons: List[str] = []
    if trend_dir != "Neutral":
        reasons.append(f"EMA stack {trend_dir}")
    if adx_val >= 22:
        reasons.append(f"ADX {adx_val:.0f} strong")
    if abs(hist_d) > 0 and abs(hist_val) > 0:
        reasons.append("MACD accel")
    if vol_ratio >= 1.2:
        reasons.append(f"Vol spike x{vol_ratio:.2f}")
    if bb_w_d > 0:
        reasons.append("BB width expanding")
    if rsi_val >= 60:
        reasons.append(f"RSI {rsi_val:.0f} bullish")
    elif rsi_val <= 40:
        reasons.append(f"RSI {rsi_val:.0f} bearish")
    if conflict:
        reasons.append("Trend/Momentum conflict")

    signal_reason = " + ".join(reasons[:6]) if reasons else "No strong edges (flat conditions)"

    return {
        "TMV Score": round(float(tmv), 2),
        "Confidence": round(float(conf), 2),
        "Trend Direction": trend_dir,
        "Regime": regime,
        "Reversal Probability": round(float(reversal_prob), 2),
        "CandleTime": candle_time,
        "SignalReason": signal_reason,

        # Optional diagnostics (useful for debugging/iteration)
        "TrendScore": round(float(trend_score), 2),
        "MomentumScore": round(float(momentum_score), 2),
        "VolumeScore": round(float(volume_score), 2),
        "VolatilityScore": round(float(volat_score), 2),
    }
