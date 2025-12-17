# tmv_updater.py
import os
import time
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

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

# Market hours (IST)
MARKET_OPEN_HHMM = (9, 15)
MARKET_CLOSE_HHMM = (15, 35)

# OHLC fetch depth (make indicators meaningful)
OHLC_INTERVAL = os.getenv("OHLC_INTERVAL", "15minute")
OHLC_DAYS = int(os.getenv("OHLC_DAYS", "20"))  # ↑ use 15–25 trading days for stability

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("tmv_updater")

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def now_ist() -> datetime:
    return datetime.now(IST)

def now_ist_iso() -> str:
    return now_ist().replace(microsecond=0).isoformat()

def is_market_hours(dt: datetime) -> bool:
    if dt.weekday() >= 5:  # Sat/Sun
        return False
    oh, om = MARKET_OPEN_HHMM
    ch, cm = MARKET_CLOSE_HHMM
    start = dt.replace(hour=oh, minute=om, second=0, microsecond=0)
    end = dt.replace(hour=ch, minute=cm, second=0, microsecond=0)
    return start <= dt <= end

def retry_gsheets(fn, *, tries: int = 6, base_sleep: float = 1.25):
    """
    Retries Google Sheets calls on 429/5xx.
    """
    for i in range(tries):
        try:
            return fn()
        except APIError as e:
            msg = str(e)
            # 429 quota / rate limit or transient backend errors
            if ("429" in msg) or ("Quota exceeded" in msg) or ("503" in msg) or ("500" in msg):
                sleep_s = base_sleep * (2 ** i)
                logger.warning("Google Sheets APIError retry %d/%d: %s | sleeping %.1fs", i+1, tries, msg, sleep_s)
                time.sleep(sleep_s)
                continue
            raise
    raise RuntimeError("Google Sheets retries exhausted (still failing).")

def get_or_create_ws(sh: gspread.Spreadsheet, title: str, rows: int = 2000, cols: int = 26) -> gspread.Worksheet:
    """
    Returns worksheet if exists, otherwise creates it.
    """
    try:
        return sh.worksheet(title)
    except WorksheetNotFound:
        logger.warning("Worksheet '%s' not found. Creating it.", title)
        return sh.add_worksheet(title=title, rows=rows, cols=cols)

def normalize_symbol(s: str) -> str:
    return (s or "").strip().upper().replace("-", "_")

# ─────────────────────────────────────────────────────────────
# Load symbols
# ─────────────────────────────────────────────────────────────
def load_watchlist(sh: gspread.Spreadsheet) -> List[str]:
    """
    Reads watchlist from column A.
    If WATCHLIST_WS doesn't exist, falls back to first worksheet.
    """
    try:
        ws = sh.worksheet(WATCHLIST_WS)
    except WorksheetNotFound:
        logger.warning("Watchlist worksheet '%s' not found. Falling back to first worksheet.", WATCHLIST_WS)
        ws = sh.get_worksheet(0)

    raw = retry_gsheets(lambda: ws.col_values(1))  # column A
    symbols: List[str] = []
    for s in raw[1:]:  # skip header
        sym = normalize_symbol(s)
        if sym:
            symbols.append(sym)

    # de-dup preserve order
    symbols = list(dict.fromkeys(symbols))
    logger.info("Loaded %d symbols from watchlist (%s)", len(symbols), ws.title)
    return symbols

# ─────────────────────────────────────────────────────────────
# Compute TMV table
# ─────────────────────────────────────────────────────────────
def compute_livescores(symbols: List[str]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    as_of = now_ist_iso()

    for sym in symbols:
        try:
            ohlc = fetch_ohlc_data(sym, interval=OHLC_INTERVAL, days=OHLC_DAYS)

            if ohlc is None or ohlc.empty:
                logger.warning("No OHLC for %s", sym)
                continue

            df = ohlc.reset_index()
            if "date" not in df.columns:
                df.rename(columns={df.columns[0]: "date"}, inplace=True)

            scores = calculate_scores(df)
            tmv = scores.get("TMV Score", None)

            if tmv is None:
                logger.warning("TMV Score missing/None for %s | reason=%s", sym, scores.get("SignalReason"))
                continue

            row = {
                # Core columns expected by your Streamlit dashboard
                "Symbol": sym,
                "TMV Score": tmv,
                "Confidence": scores.get("Confidence"),
                "Trend Direction": scores.get("Trend Direction"),
                "Regime": scores.get("Regime"),
                "Reversal Probability": scores.get("Reversal Probability"),
                "CandleTime": scores.get("CandleTime"),
                "AsOf": as_of,

                # New "meaningful" columns (make ranking explainable)
                "SignalReason": scores.get("SignalReason"),
                "TrendScore": scores.get("TrendScore"),
                "MomentumScore": scores.get("MomentumScore"),
                "VolumeScore": scores.get("VolumeScore"),
                "VolatilityScore": scores.get("VolatilityScore"),
            }

            rows.append(row)

        except Exception as e:
            logger.exception("Error processing %s: %s", sym, e)

    df_out = pd.DataFrame(rows)
    if df_out.empty:
        logger.error("No TMV rows generated.")
        return df_out

    # Normalize headers
    df_out.columns = [str(c).strip() for c in df_out.columns]

    # Ensure TMV Score exists
    if "TMV Score" not in df_out.columns:
        raise RuntimeError("TMV Score column missing AFTER computation (should never happen).")

    return df_out

# ─────────────────────────────────────────────────────────────
# Write to Google Sheet (quota-safe + stable headers)
# ─────────────────────────────────────────────────────────────
def write_livescores(sh: gspread.Spreadsheet, df: pd.DataFrame):
    ws = get_or_create_ws(sh, LIVESCORE_WS, rows=5000, cols=30)

    preferred_order = [
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
        "AsOf",
    ]

    final_cols = [c for c in preferred_order if c in df.columns]
    final_cols += [c for c in df.columns if c not in final_cols]
    df = df[final_cols].copy()

    # Convert to strings for Sheets
    values = [df.columns.tolist()] + df.astype(str).values.tolist()

    # Clear + update in one go (fewer API calls)
    def _write():
        ws.clear()
        ws.update("A1", values)

    retry_gsheets(_write)

    logger.info("LiveScores updated: %d rows | cols=%d | ws=%s", len(df), len(df.columns), ws.title)

# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
def main():
    dt = now_ist()
    if not is_market_hours(dt):
        logger.info("Market closed (IST %s). Skipping update to avoid fake freshness.", dt.strftime("%Y-%m-%d %H:%M:%S"))
        return

    gc = get_gspread_client()
    sh = retry_gsheets(lambda: gc.open_by_key(BACKGROUND_SHEET_KEY))

    symbols = load_watchlist(sh)
    if not symbols:
        logger.error("Watchlist empty. Aborting.")
        return

    df = compute_livescores(symbols)
    if df.empty:
        logger.error("No data to write. Aborting.")
        return

    write_livescores(sh, df)

if __name__ == "__main__":
    main()
