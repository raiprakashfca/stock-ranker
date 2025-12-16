# tmv_updater.py
import os
import logging
from datetime import datetime
from typing import List

import pandas as pd
import pytz

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("tmv_updater")


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def now_ist_iso() -> str:
    return datetime.now(IST).replace(microsecond=0).isoformat()


def get_worksheet_safe(sh, title: str):
    """Return worksheet by name, else fallback to first worksheet."""
    try:
        return sh.worksheet(title)
    except Exception:
        ws = sh.get_worksheet(0)
        logger.warning(
            "Worksheet '%s' not found. Falling back to first worksheet '%s'.",
            title,
            ws.title,
        )
        return ws


# ─────────────────────────────────────────────────────────────
# Load symbols
# ─────────────────────────────────────────────────────────────
def load_watchlist(gc) -> List[str]:
    sh = gc.open_by_key(BACKGROUND_SHEET_KEY)
    ws = get_worksheet_safe(sh, WATCHLIST_WS)

    raw = ws.col_values(1)
    symbols = []

    for s in raw[1:]:  # skip header
        s = (s or "").strip().upper().replace("-", "_")
        if s:
            symbols.append(s)

    symbols = list(dict.fromkeys(symbols))
    logger.info("Loaded %d symbols from worksheet '%s'", len(symbols), ws.title)
    return symbols


# ─────────────────────────────────────────────────────────────
# Compute TMV
# ─────────────────────────────────────────────────────────────
def compute_livescores(symbols: List[str]) -> pd.DataFrame:
    rows = []
    as_of = now_ist_iso()

    for sym in symbols:
        try:
            ohlc = fetch_ohlc_data(sym, interval="15minute", days=10)
            if ohlc is None or ohlc.empty:
                continue

            df = ohlc.reset_index()
            if "date" not in df.columns:
                df.rename(columns={df.columns[0]: "date"}, inplace=True)

            scores = calculate_scores(df)
            if not scores or "TMV Score" not in scores:
                continue

            rows.append(
                {
                    "Symbol": sym,
                    "TMV Score": scores.get("TMV Score"),
                    "Confidence": scores.get("Confidence"),
                    "Trend Direction": scores.get("Trend Direction"),
                    "Regime": scores.get("Regime"),
                    "Reversal Probability": scores.get("Reversal Probability"),
                    "CandleTime": scores.get("CandleTime"),
                    "AsOf": as_of,
                }
            )

        except Exception:
            logger.exception("Error processing %s", sym)

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────
# Write to sheet
# ─────────────────────────────────────────────────────────────
def write_livescores(gc, df: pd.DataFrame):
    sh = gc.open_by_key(BACKGROUND_SHEET_KEY)

    try:
        ws = sh.worksheet(LIVESCORE_WS)
    except Exception:
        logger.warning("Worksheet '%s' not found. Creating it.", LIVESCORE_WS)
        ws = sh.add_worksheet(title=LIVESCORE_WS, rows="500", cols="20")

    ws.update(
        "A1",
        [df.columns.tolist()] + df.astype(str).values.tolist(),
    )

    logger.info("LiveScores written to '%s' (%d rows)", ws.title, len(df))


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
def main():
    gc = get_gspread_client()

    symbols = load_watchlist(gc)
    if not symbols:
        logger.error("No symbols found. Aborting.")
        return

    df = compute_livescores(symbols)
    if df.empty:
        logger.error("No TMV data generated. Aborting.")
        return

    write_livescores(gc, df)


if __name__ == "__main__":
    main()
