# tmv_updater.py
import os
import time
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

import pandas as pd
import pytz
import gspread
from gspread.exceptions import WorksheetNotFound, APIError

from utils.google_client import get_gspread_client
from utils.indicators import calculate_scores
from fetch_ohlc import fetch_ohlc_data

# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────
IST = pytz.timezone("Asia/Kolkata")

BACKGROUND_SHEET_KEY = os.getenv(
    "BACKGROUND_SHEET_KEY",
    "1Cpgj1M_ofN1SqvuqDDHuN7Gy17tfkhy4fCCP8Mx7bRI",
)

WATCHLIST_WS = os.getenv("WATCHLIST_WORKSHEET", "Watchlist")
LIVESCORE_WS = os.getenv("LIVESCORE_WORKSHEET", "LiveScores")
BASELINE_WS = os.getenv("BASELINE_WORKSHEET", "Baseline915")  # NEW

# Market hours (IST)
MARKET_OPEN_HHMM = (9, 15)
MARKET_CLOSE_HHMM = (15, 35)

# Baseline capture window (IST)
BASELINE_START_HHMM = (9, 15)
BASELINE_END_HHMM = (9, 30)  # capture once per day between 9:15–9:30

# OHLC fetch depth
OHLC_INTERVAL = os.getenv("OHLC_INTERVAL", "15minute")
OHLC_DAYS = int(os.getenv("OHLC_DAYS", "20"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("tmv_updater")


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def now_ist() -> datetime:
    return datetime.now(IST)

def now_ist_iso() -> str:
    return now_ist().replace(microsecond=0).isoformat()

def today_ist_str() -> str:
    return now_ist().strftime("%Y-%m-%d")

def _time_in_range(dt: datetime, start_hm, end_hm) -> bool:
    sh, sm = start_hm
    eh, em = end_hm
    start = dt.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end = dt.replace(hour=eh, minute=em, second=0, microsecond=0)
    return start <= dt <= end

def is_market_hours(dt: datetime) -> bool:
    if dt.weekday() >= 5:
        return False
    return _time_in_range(dt, MARKET_OPEN_HHMM, MARKET_CLOSE_HHMM)

def is_baseline_window(dt: datetime) -> bool:
    if dt.weekday() >= 5:
        return False
    return _time_in_range(dt, BASELINE_START_HHMM, BASELINE_END_HHMM)

def retry_gsheets(fn, *, tries: int = 6, base_sleep: float = 1.25):
    for i in range(tries):
        try:
            return fn()
        except APIError as e:
            msg = str(e)
            if ("429" in msg) or ("Quota exceeded" in msg) or ("503" in msg) or ("500" in msg):
                sleep_s = base_sleep * (2 ** i)
                logger.warning("Google Sheets retry %d/%d: %s | sleeping %.1fs", i + 1, tries, msg, sleep_s)
                time.sleep(sleep_s)
                continue
            raise
    raise RuntimeError("Google Sheets retries exhausted.")

def get_or_create_ws(sh: gspread.Spreadsheet, title: str, rows: int = 5000, cols: int = 40) -> gspread.Worksheet:
    try:
        return sh.worksheet(title)
    except WorksheetNotFound:
        logger.warning("Worksheet '%s' not found. Creating it.", title)
        return sh.add_worksheet(title=title, rows=rows, cols=cols)

def normalize_symbol(s: str) -> str:
    return (s or "").strip().upper().replace("-", "_")


# ─────────────────────────────────────────────────────────────
# Watchlist
# ─────────────────────────────────────────────────────────────
def load_watchlist(sh: gspread.Spreadsheet) -> List[str]:
    try:
        ws = sh.worksheet(WATCHLIST_WS)
    except WorksheetNotFound:
        logger.warning("Watchlist worksheet '%s' not found. Falling back to first worksheet.", WATCHLIST_WS)
        ws = sh.get_worksheet(0)

    raw = retry_gsheets(lambda: ws.col_values(1))
    symbols: List[str] = []
    for s in raw[1:]:
        sym = normalize_symbol(s)
        if sym:
            symbols.append(sym)

    symbols = list(dict.fromkeys(symbols))
    logger.info("Loaded %d symbols from watchlist (%s)", len(symbols), ws.title)
    return symbols


# ─────────────────────────────────────────────────────────────
# Baseline read/write
# ─────────────────────────────────────────────────────────────
BASELINE_COLUMNS = [
    "BaselineDate",
    "Symbol",
    "TMV Score",
    "Confidence",
    "Trend Direction",
    "Regime",
    "Reversal Probability",
    "SignalReason",
    "TrendScore",
    "MomentumScore",
    "VolumeScore",
    "VolatilityScore",
    "CandleTime",
    "CapturedAt",
]

def read_baseline_map(sh: gspread.Spreadsheet) -> Dict[str, Dict[str, Any]]:
    """
    Returns map: Symbol -> baseline row (only for today's baseline).
    If baseline not found or different date, returns empty map.
    """
    ws = get_or_create_ws(sh, BASELINE_WS)
    values = retry_gsheets(lambda: ws.get_all_values())
    if not values or len(values) < 2:
        return {}

    headers = [h.strip() for h in values[0]]
    df = pd.DataFrame(values[1:], columns=headers)

    if "BaselineDate" not in df.columns or "Symbol" not in df.columns:
        return {}

    df["BaselineDate"] = df["BaselineDate"].astype(str).str.strip()
    df["Symbol"] = df["Symbol"].astype(str).str.strip().str.upper()

    td = today_ist_str()
    df_today = df[df["BaselineDate"] == td].copy()
    if df_today.empty:
        return {}

    out: Dict[str, Dict[str, Any]] = {}
    for _, r in df_today.iterrows():
        out[r["Symbol"]] = r.to_dict()
    return out

def write_baseline(sh: gspread.Spreadsheet, df_baseline: pd.DataFrame):
    ws = get_or_create_ws(sh, BASELINE_WS)

    # Force stable columns
    for c in BASELINE_COLUMNS:
        if c not in df_baseline.columns:
            df_baseline[c] = ""

    df_baseline = df_baseline[BASELINE_COLUMNS].copy()

    values = [df_baseline.columns.tolist()] + df_baseline.astype(str).values.tolist()

    def _write():
        ws.clear()
        ws.update("A1", values)

    retry_gsheets(_write)
    logger.info("Baseline written: %d rows | ws=%s", len(df_baseline), ws.title)


# ─────────────────────────────────────────────────────────────
# Compute TMV rows
# ─────────────────────────────────────────────────────────────
def compute_scores_for_symbol(sym: str) -> Optional[Dict[str, Any]]:
    ohlc = fetch_ohlc_data(sym, interval=OHLC_INTERVAL, days=OHLC_DAYS)
    if ohlc is None or ohlc.empty:
        return None

    df = ohlc.reset_index()
    if "date" not in df.columns:
        df.rename(columns={df.columns[0]: "date"}, inplace=True)

    scores = calculate_scores(df)
    if scores.get("TMV Score", None) is None:
        return None
    return scores

def _num(x) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None

def compute_livescores(symbols: List[str], baseline_map: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    as_of = now_ist_iso()
    td = today_ist_str()

    for sym in symbols:
        try:
            scores = compute_scores_for_symbol(sym)
            if not scores:
                logger.warning("No scores for %s", sym)
                continue

            base = baseline_map.get(sym)

            tmv_now = _num(scores.get("TMV Score"))
            tr_now = _num(scores.get("TrendScore"))
            mo_now = _num(scores.get("MomentumScore"))
            vo_now = _num(scores.get("VolumeScore"))
            vl_now = _num(scores.get("VolatilityScore"))

            base_tmv = _num(base.get("TMV Score")) if base else None
            base_tr = _num(base.get("TrendScore")) if base else None
            base_mo = _num(base.get("MomentumScore")) if base else None
            base_vo = _num(base.get("VolumeScore")) if base else None
            base_vl = _num(base.get("VolatilityScore")) if base else None

            row = {
                "Symbol": sym,

                # Live scores
                "TMV Score": tmv_now,
                "Confidence": scores.get("Confidence"),
                "Trend Direction": scores.get("Trend Direction"),
                "Regime": scores.get("Regime"),
                "Reversal Probability": scores.get("Reversal Probability"),
                "SignalReason": scores.get("SignalReason"),
                "TrendScore": tr_now,
                "MomentumScore": mo_now,
                "VolumeScore": vo_now,
                "VolatilityScore": vl_now,

                "CandleTime": scores.get("CandleTime"),
                "AsOf": as_of,

                # Baseline + deltas (NEW)
                "BaselineDate": td if base else "",
                "Base TMV": base_tmv if base else "",
                "TMV Δ": (tmv_now - base_tmv) if (tmv_now is not None and base_tmv is not None) else "",
                "Trend Δ": (tr_now - base_tr) if (tr_now is not None and base_tr is not None) else "",
                "Momentum Δ": (mo_now - base_mo) if (mo_now is not None and base_mo is not None) else "",
                "Volume Δ": (vo_now - base_vo) if (vo_now is not None and base_vo is not None) else "",
                "Volatility Δ": (vl_now - base_vl) if (vl_now is not None and base_vl is not None) else "",
            }

            rows.append(row)

        except Exception as e:
            logger.exception("Error processing %s: %s", sym, e)

    df_out = pd.DataFrame(rows)
    if df_out.empty:
        logger.error("No TMV rows generated.")
        return df_out

    df_out.columns = [str(c).strip() for c in df_out.columns]
    return df_out


# ─────────────────────────────────────────────────────────────
# Write LiveScores
# ─────────────────────────────────────────────────────────────
def write_livescores(sh: gspread.Spreadsheet, df: pd.DataFrame):
    ws = get_or_create_ws(sh, LIVESCORE_WS)

    preferred_order = [
        "Symbol",
        "TMV Score",
        "TMV Δ",
        "Base TMV",
        "Confidence",
        "Trend Direction",
        "Regime",
        "SignalReason",
        "Reversal Probability",
        "TrendScore",
        "Trend Δ",
        "MomentumScore",
        "Momentum Δ",
        "VolumeScore",
        "Volume Δ",
        "VolatilityScore",
        "Volatility Δ",
        "CandleTime",
        "AsOf",
        "BaselineDate",
    ]

    final_cols = [c for c in preferred_order if c in df.columns]
    final_cols += [c for c in df.columns if c not in final_cols]
    df = df[final_cols].copy()

    values = [df.columns.tolist()] + df.astype(str).values.tolist()

    def _write():
        ws.clear()
        ws.update("A1", values)

    retry_gsheets(_write)
    logger.info("LiveScores updated: %d rows | ws=%s", len(df), ws.title)


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
def main():
    dt = now_ist()
    if not is_market_hours(dt):
        logger.info("Market closed (IST %s). Skipping update.", dt.strftime("%Y-%m-%d %H:%M:%S"))
        return

    gc = get_gspread_client()
    sh = retry_gsheets(lambda: gc.open_by_key(BACKGROUND_SHEET_KEY))

    symbols = load_watchlist(sh)
    if not symbols:
        logger.error("Watchlist empty. Aborting.")
        return

    # 1) Ensure baseline exists for today (capture once in baseline window)
    baseline_map = read_baseline_map(sh)
    if is_baseline_window(dt) and not baseline_map:
        logger.info("Baseline window detected and baseline missing. Capturing baseline now...")
        td = today_ist_str()
        captured_at = now_ist_iso()

        baseline_rows = []
        for sym in symbols:
            scores = compute_scores_for_symbol(sym)
            if not scores:
                continue
            baseline_rows.append({
                "BaselineDate": td,
                "Symbol": sym,
                "TMV Score": scores.get("TMV Score"),
                "Confidence": scores.get("Confidence"),
                "Trend Direction": scores.get("Trend Direction"),
                "Regime": scores.get("Regime"),
                "Reversal Probability": scores.get("Reversal Probability"),
                "SignalReason": scores.get("SignalReason"),
                "TrendScore": scores.get("TrendScore"),
                "MomentumScore": scores.get("MomentumScore"),
                "VolumeScore": scores.get("VolumeScore"),
                "VolatilityScore": scores.get("VolatilityScore"),
                "CandleTime": scores.get("CandleTime"),
                "CapturedAt": captured_at,
            })

        df_baseline = pd.DataFrame(baseline_rows)
        if not df_baseline.empty:
            write_baseline(sh, df_baseline)
            baseline_map = read_baseline_map(sh)
        else:
            logger.warning("Baseline capture produced no rows (data unavailable).")

    # 2) Compute live scores + deltas vs baseline (if baseline exists)
    df_live = compute_livescores(symbols, baseline_map)
    if df_live.empty:
        logger.error("No live data to write. Aborting.")
        return

    write_livescores(sh, df_live)

if __name__ == "__main__":
    main()
