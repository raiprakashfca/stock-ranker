# tmv_updater.py
"""
TMV Updater (Authoritative Writer to Google Sheet)

- Loads watchlist symbols from BackgroundAnalysisStore / Watchlist
- Fetches 15m OHLC data via Zerodha for each symbol
- Computes TMV scores with indicators.calculate_scores
- Writes results to BackgroundAnalysisStore / LiveScores with:
    - AsOf (IST timestamp) on every row
    - Watchdog LastRun timestamp in H1
"""

import logging
from datetime import datetime
from typing import List

import pandas as pd
import pytz

from utils.token_utils import get_gsheet_client
from utils.fetch_ohlc import fetch_ohlc_data
from utils.indicators import calculate_scores

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("tmv_updater")

IST = pytz.timezone("Asia/Kolkata")

WORKBOOK_NAME = "BackgroundAnalysisStore"
WATCHLIST_SHEET = "Watchlist"
LIVESCORES_SHEET = "LiveScores"


def load_watchlist_symbols() -> List[str]:
    """Read symbols from BackgroundAnalysisStore / Watchlist (column A, after header)."""
    client = get_gsheet_client()
    ws = client.open(WORKBOOK_NAME).worksheet(WATCHLIST_SHEET)
    values = ws.get_all_values()

    symbols: List[str] = []
    for row in values[1:]:  # skip header
        if not row:
            continue
        sym = (row[0] or "").strip().upper()
        if sym:
            symbols.append(sym)

    return symbols


def compute_tmv_table(symbols: List[str]) -> pd.DataFrame:
    """Compute TMV table and attach a single IST timestamp to all rows."""
    rows = []
    as_of = datetime.now(IST).replace(microsecond=0).isoformat()

    for sym in symbols:
        try:
            # Use your existing 15m OHLC fetcher
            df_ohlc = fetch_ohlc_data(sym, interval="15minute", days=7)
            if df_ohlc is None or df_ohlc.empty:
                logger.warning("No OHLC data for %s", sym)
                continue

            scores = calculate_scores(df_ohlc.copy())
            if not scores:
                logger.warning("No TMV scores for %s", sym)
                continue

            row = {"Symbol": sym}
            row.update(scores)
            row["AsOf"] = as_of  # IST timestamp

            rows.append(row)

        except Exception as e:
            logger.exception("Error computing TMV for %s: %s", sym, e)

    return pd.DataFrame(rows)


def write_livescores(df: pd.DataFrame) -> None:
    """Write TMV table + AsOf to BackgroundAnalysisStore / LiveScores and update H1 watchdog."""
    client = get_gsheet_client()
    ws = client.open(WORKBOOK_NAME).worksheet(LIVESCORES_SHEET)

    if df.empty:
        logger.warning("TMV Updater: DataFrame is empty, clearing LiveScores.")
        ws.clear()
        return

    # Round numeric values a bit for cleanliness
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            df[col] = df[col].round(2)

    # Prepare values
    values = [df.columns.tolist()] + df.values.tolist()

    # Clear + write starting at A1
    ws.clear()
    ws.update("A1", values)

    # Watchdog: last successful run time in H1 (or any suitable cell)
    try:
        now_ist = datetime.now(IST).replace(microsecond=0).isoformat()
        ws.update("H1", now_ist)
    except Exception as e:
        logger.warning("Failed to update watchdog cell H1: %s", e)


def main():
    logger.info("Starting TMV updater...")

    symbols = load_watchlist_symbols()
    if not symbols:
        logger.error("No symbols found in Watchlist. Aborting.")
        return

    df = compute_tmv_table(symbols)
    if df.empty:
        logger.error("TMV updater produced empty DataFrame. Aborting.")
        return

    write_livescores(df)

    logger.info("TMV updater completed successfully with %d rows.", len(df))


if __name__ == "__main__":
    main()
