# tmv_updater.py
import os
import time
import logging
from datetime import datetime, date
from typing import List, Dict, Any, Optional

import pandas as pd
import pytz

from utils.google_client import get_gspread_client
from fetch_ohlc import fetch_ohlc_data
from utils.indicators import calculate_scores  # you will replace indicators.py below

IST = pytz.timezone("Asia/Kolkata")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("tmv_updater")

# Sheet config
BACKGROUND_SHEET_KEY = os.getenv("BACKGROUND_SHEET_KEY", "").strip()
WATCHLIST_WS = os.getenv("WATCHLIST_WORKSHEET", "Watchlist")
LIVESCORES_WS = os.getenv("LIVESCORE_WORKSHEET", "LiveScores")

# Baseline & meta
BASELINE_WS = os.getenv("BASELINE_WORKSHEET", "TMV_Baseline_915")
META_WS = os.getenv("META_WORKSHEET", "Meta")

# Quality thresholds
MAX_CANDLE_AGE_MIN_OK = float(os.getenv("MAX_CANDLE_AGE_MIN_OK", "20"))  # 15m candle should be < ~20m old during market
MAX_CANDLE_AGE_MIN_STALE = float(os.getenv("MAX_CANDLE_AGE_MIN_STALE", "90"))

# Small backoff to be nice to APIs
SLEEP_BETWEEN_SYMBOLS_SEC = float(os.getenv("SLEEP_BETWEEN_SYMBOLS_SEC", "0.25"))


def now_ist() -> datetime:
    return datetime.now(IST).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def ensure_worksheet(ss, title: str):
    try:
        return ss.worksheet(title)
    except Exception:
        logger.info("Worksheet '%s' not found. Creating it.", title)
        return ss.add_worksheet(title=title, rows=1000, cols=40)


def load_watchlist_symbols(ss) -> List[str]:
    ws = ss.worksheet(WATCHLIST_WS)
    values = ws.get_all_values()
    out: List[str] = []
    for row in values[1:]:
        if not row:
            continue
        sym = (row[0] or "").strip().upper().replace("-", "_")
        if sym:
            out.append(sym)
    # de-dup preserve order
    out = list(dict.fromkeys(out))
    return out


def _candle_time_from_ohlc(df: pd.DataFrame) -> Optional[datetime]:
    if df is None or df.empty:
        return None
    # df is indexed by datetime in your fetch_ohlc.py
    idx = df.index
    if len(idx) == 0:
        return None
    dt = pd.to_datetime(idx[-1])
    # Normalize to IST aware
    if getattr(dt, "tzinfo", None) is None:
        return IST.localize(dt.to_pydatetime())
    return dt.tz_convert(IST).to_pydatetime()


def _quality_from_candle_age(age_min: Optional[float]) -> str:
    if age_min is None:
        return "UNKNOWN"
    if age_min <= MAX_CANDLE_AGE_MIN_OK:
        return "OK"
    if age_min <= MAX_CANDLE_AGE_MIN_STALE:
        return "STALE"
    return "UNKNOWN"


def _read_baseline_for_today(bws) -> Dict[str, float]:
    """
    Baseline sheet format:
      Date | Symbol | Base TMV
    """
    values = bws.get_all_values()
    if not values or len(values) < 2:
        return {}
    headers = [h.strip() for h in values[0]]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=headers)
    if "Date" not in df.columns or "Symbol" not in df.columns or "Base TMV" not in df.columns:
        return {}

    today_str = date.today().isoformat()
    df = df[df["Date"] == today_str].copy()
    if df.empty:
        return {}

    df["Base TMV"] = pd.to_numeric(df["Base TMV"], errors="coerce")
    df = df.dropna(subset=["Base TMV"])
    return {r["Symbol"].strip().upper(): float(r["Base TMV"]) for _, r in df.iterrows()}


def _maybe_write_baseline(ss, bws, rows: List[Dict[str, Any]]) -> None:
    """
    If time is within 09:15–09:25 IST and baseline for today is missing,
    write baseline for all symbols present in current run.
    """
    t = now_ist().time()
    if not (t.hour == 9 and 15 <= t.minute <= 25):
        return

    existing = _read_baseline_for_today(bws)
    if existing:
        return  # already captured

    today_str = date.today().isoformat()
    payload = [["Date", "Symbol", "Base TMV"]]
    for r in rows:
        sym = r.get("Symbol")
        tmv = r.get("TMV Score")
        if sym and tmv is not None:
            payload.append([today_str, sym, tmv])

    if len(payload) <= 1:
        return

    bws.clear()
    bws.update("A1", payload)
    logger.info("✅ Baseline captured for %d symbols (sheet: %s)", len(payload) - 1, BASELINE_WS)


def compute_rows(symbols: List[str], baseline_map: Dict[str, float]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    as_of = now_ist()

    for sym in symbols:
        try:
            ohlc = fetch_ohlc_data(sym, interval="15minute", days=10)
            candle_dt = _candle_time_from_ohlc(ohlc)
            candle_age = None
            if candle_dt:
                candle_age = round((as_of - candle_dt).total_seconds() / 60.0, 1)

            scores = calculate_scores(ohlc)  # accepts indexed OHLC (see indicators.py below)
            if not scores:
                logger.warning("No scores for %s (insufficient candles or indicator failure)", sym)
                continue

            tmv = scores.get("TMV Score")
            base = baseline_map.get(sym)
            tmv_delta = round(float(tmv) - float(base), 2) if (tmv is not None and base is not None) else None

            row = {
                "Symbol": sym,

                # Keep both names to prevent app-side mismatch
                "TMV Score": tmv,
                "15m TMV Score": tmv,

                "Trend Direction": scores.get("Trend Direction"),
                "Regime": scores.get("Regime"),
                "Confidence": scores.get("Confidence"),
                "SignalReason": scores.get("SignalReason"),
                "Reversal Probability": scores.get("Reversal Probability"),

                "AsOf": iso(as_of),
                "CandleTime": iso(candle_dt) if candle_dt else "",
                "CandleAgeMin": candle_age,

                "Base TMV": base if base is not None else "",
                "TMV Δ": tmv_delta if tmv_delta is not None else "",

                "DataQuality": _quality_from_candle_age(candle_age),
            }
            rows.append(row)

        except Exception as e:
            logger.exception("Error for %s: %s", sym, e)

        time.sleep(SLEEP_BETWEEN_SYMBOLS_SEC)

    return rows


def write_table(ws, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        ws.clear()
        return

    # Stable column order
    cols = [
        "Symbol",
        "15m TMV Score",
        "TMV Score",
        "TMV Δ",
        "Base TMV",
        "Trend Direction",
        "Regime",
        "Confidence",
        "SignalReason",
        "Reversal Probability",
        "CandleTime",
        "CandleAgeMin",
        "AsOf",
        "DataQuality",
    ]

    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df.columns:
            df[c] = ""

    df = df[cols].copy()

    # Light rounding for display
    for c in ["15m TMV Score", "TMV Score", "TMV Δ", "Base TMV", "Reversal Probability", "CandleAgeMin"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").round(2)

    values = [df.columns.tolist()] + df.fillna("").astype(str).values.tolist()

    ws.clear()
    ws.update("A1", values)


def write_meta(meta_ws, status: str, message: str = "") -> None:
    meta_ws.clear()
    meta_ws.update(
        "A1",
        [
            ["LastRunIST", "Status", "Message"],
            [iso(now_ist()), status, message[:200]],
        ],
    )


def main():
    if not BACKGROUND_SHEET_KEY:
        raise RuntimeError("Missing BACKGROUND_SHEET_KEY env/secret.")

    gc = get_gspread_client()
    ss = gc.open_by_key(BACKGROUND_SHEET_KEY)

    lives_ws = ensure_worksheet(ss, LIVESCORES_WS)
    base_ws = ensure_worksheet(ss, BASELINE_WS)
    meta_ws = ensure_worksheet(ss, META_WS)

    try:
        symbols = load_watchlist_symbols(ss)
        if not symbols:
            write_meta(meta_ws, "ERROR", "Watchlist empty.")
            logger.error("Watchlist empty. Aborting.")
            return

        baseline_map = _read_baseline_for_today(base_ws)

        rows = compute_rows(symbols, baseline_map)

        # Optionally capture baseline around 9:15
        _maybe_write_baseline(ss, base_ws, rows)

        if not rows:
            write_meta(meta_ws, "ERROR", "No rows computed (all failed).")
            logger.error("No rows computed. Aborting.")
            return

        write_table(lives_ws, rows)
        write_meta(meta_ws, "OK", f"Wrote {len(rows)} rows to {LIVESCORES_WS}")

        logger.info("✅ TMV updater completed: %d rows", len(rows))

    except Exception as e:
        write_meta(meta_ws, "ERROR", str(e))
        raise


if __name__ == "__main__":
    main()
