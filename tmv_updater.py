# tmv_updater.py
"""
TMV Updater (Authoritative Google Sheet Writer)

This script:
- Loads watchlist symbols from BackgroundAnalysisStore / Watchlist
- Fetches OHLC data for each symbol
- Computes TMV scores (Trend, Momentum, Volume)
- Writes the output to BackgroundAnalysisStore / LiveScores with:
    - AsOf IST timestamp per row
    - LastRun cell (H1) for watchdog
"""

import logging
from datetime import datetime
from typing import List
import pandas as pd
import pytz

from utils.google_client import get_gspread_client
from utils.ohlc import fetch_ohlc
from utils.indicators import calculate_scores
from utils.sheet_logger import log_to_google_sheets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger("tmv_updater")

IST = pytz.timezone("Asia/Kolkata")

WATCHLIST_BOOK = "BackgroundAnalysisStore"
WATCHLIST_SHEET = "Watchlist"
OUTPUT_BOOK = "BackgroundAnalysisStore"
OUTPUT_SHEET = "LiveScores"


def load_watchlist() -> List[str]:
    client = get_gspread_client()
    ws = client.open(WATCHLIST_BOOK).worksheet(WATCHLIST_SHEET)
    values = ws.get_all_values()

    symbols = []
    for row in values[1:]:
        if row and row[0].strip():
            symbols.append(row[0].strip().upper())

    return symbols


def compute_table(symbols: List[str]) -> pd.DataFrame:
    rows = []
    timestamp = datetime.now(IST).replace(microsecond=0).isoformat()

    for sym in symbols:
        try:
            ohlc = fetch_ohlc(sym, interval="15minute", days=7)
            if ohlc.empty:
                logger.warning("No OHLC for %s", sym)
                continue

            scores = calculate_scores(ohlc)
            if not scores:
                logger.warning("No TMV scores for %s", sym)
                continue

            row = {"Symbol": sym}
            row.update(scores)
            row["AsOf"] = timestamp  # IST timestamp for each row

            rows.append(row)

        except Exception as exc:
            logger.exception("Error computing TMV for %s: %s", sym, exc)

    return pd.DataFrame(rows)


def main():
    logger.info("Starting TMV updater...")

    symbols = load_watchlist()
    if not symbols:
        logger.error("NO WATCHLIST SYMBOLS FOUND — Aborting.")
        return

    df = compute_table(symbols)
    if df.empty:
        logger.error("TMV updater produced EMPTY DATAFRAME — Aborting.")
        return

    # Write table to Sheet
    log_to_google_sheets(
        workbook=OUTPUT_BOOK,
        sheet_name=OUTPUT_SHEET,
        df=df,
        clear=True
    )

    # Watchdog cell (H1)
    try:
        client = get_gspread_client()
        ws = client.open(OUTPUT_BOOK).worksheet(OUTPUT_SHEET)
        ws.update("H1", datetime.now(IST).isoformat())
    except Exception as exc:
        logger.warning("Could not update watchdog cell: %s", exc)

    logger.info("TMV Updater Completed Successfully with %d rows.", len(df))


if __name__ == "__main__":
    main()
